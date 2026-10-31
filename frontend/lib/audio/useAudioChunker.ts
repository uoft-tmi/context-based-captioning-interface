'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { AudioChunkBuffer } from './chunk-buffer';
import { AudioRequestPacer } from './request-pacer';

export interface AudioChunk {
  chunkIndex: number;
  audio: Blob;
  capturedAtMs: number;
  mime: 'audio/wav';
  blobSizeBytes: number;
}
interface Options {
  onChunk: (chunk: AudioChunk) => Promise<void>;
  onError: (message: string) => void;
  chunkDurationMs?: number;
  initialChunkDurationMs?: number;
  minRequestIntervalMs?: number;
}
const TARGET_SAMPLE_RATE = 16_000;
const METER_EPSILON = 1e-8;
const MIN_METER_DB = -90;
const MAX_METER_DB = -20;
const MAX_QUEUED_CHUNKS = 3;

function downsampleTo16k(
  input: Float32Array,
  sourceRate: number,
): Float32Array {
  if (sourceRate === TARGET_SAMPLE_RATE) {
    return input;
  }

  const sampleRateRatio = sourceRate / TARGET_SAMPLE_RATE;
  const targetLength = Math.round(input.length / sampleRateRatio);
  const output = new Float32Array(targetLength);

  let outputIndex = 0;
  let inputIndex = 0;

  while (outputIndex < targetLength) {
    const nextInputIndex = Math.round((outputIndex + 1) * sampleRateRatio);
    let accum = 0;
    let count = 0;

    for (let i = inputIndex; i < nextInputIndex && i < input.length; i += 1) {
      accum += input[i];
      count += 1;
    }

    output[outputIndex] = count > 0 ? accum / count : 0;
    outputIndex += 1;
    inputIndex = nextInputIndex;
  }

  return output;
}

function encodeMonoPcm16Wav(samples: Float32Array, sampleRate: number): Blob {
  const bytesPerSample = 2;
  const blockAlign = bytesPerSample;
  const byteRate = sampleRate * blockAlign;
  const dataSize = samples.length * bytesPerSample;
  const buffer = new ArrayBuffer(44 + dataSize);
  const view = new DataView(buffer);

  const writeString = (offset: number, value: string) => {
    for (let i = 0; i < value.length; i += 1) {
      view.setUint8(offset + i, value.charCodeAt(i));
    }
  };

  writeString(0, 'RIFF');
  view.setUint32(4, 36 + dataSize, true);
  writeString(8, 'WAVE');
  writeString(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, byteRate, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, 16, true);
  writeString(36, 'data');
  view.setUint32(40, dataSize, true);

  let offset = 44;
  for (let i = 0; i < samples.length; i += 1) {
    const sample = Math.max(-1, Math.min(1, samples[i]));
    const int16 = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
    view.setInt16(offset, int16, true);
    offset += bytesPerSample;
  }

  return new Blob([buffer], { type: 'audio/wav' });
}

function downmixChannelsToMono(channels: Float32Array[]): Float32Array {
  const channelCount = channels.length;
  const sampleCount = channels[0]?.length ?? 0;

  if (sampleCount === 0 || channelCount === 0) {
    return new Float32Array(0);
  }

  if (channelCount <= 1) {
    const mono = new Float32Array(sampleCount);
    mono.set(channels[0]);
    return mono;
  }

  const mono = new Float32Array(sampleCount);
  for (let channel = 0; channel < channelCount; channel += 1) {
    const samples = channels[channel];
    for (let i = 0; i < sampleCount; i += 1) {
      mono[i] += samples[i];
    }
  }

  const invChannelCount = 1 / channelCount;
  for (let i = 0; i < sampleCount; i += 1) {
    mono[i] *= invChannelCount;
  }

  return mono;
}

function computeAudioLevel(samples: Float32Array): number {
  if (samples.length === 0) {
    return 0;
  }

  let sumSquares = 0;
  let peak = 0;
  for (let i = 0; i < samples.length; i += 1) {
    const sample = samples[i];
    const absSample = Math.abs(sample);
    if (absSample > peak) {
      peak = absSample;
    }
    sumSquares += sample * sample;
  }

  const rms = Math.sqrt(sumSquares / samples.length);

  // Use both RMS and peak to keep the meter responsive on quiet microphones.
  const signal = Math.max(rms, peak * 0.5);
  const db = 20 * Math.log10(Math.max(signal, METER_EPSILON));
  const normalized = (db - MIN_METER_DB) / (MAX_METER_DB - MIN_METER_DB);
  return Math.max(0, Math.min(1, normalized));
}

export function useAudioChunker({ onChunk, onError, chunkDurationMs = 2500, initialChunkDurationMs, minRequestIntervalMs = 0 }: Options) {
  const [isRecording, setIsRecording] = useState(false);
  const [audioLevel, setAudioLevel] = useState(0);
  const [chunkCount, setChunkCount] = useState(0);
  const callbacks = useRef({ onChunk, onError });
  useEffect(() => { callbacks.current = { onChunk, onError }; }, [onChunk, onError]);
  const stream = useRef<MediaStream | null>(null);
  const context = useRef<AudioContext | null>(null);
  const source = useRef<MediaStreamAudioSourceNode | null>(null);
  const worklet = useRef<AudioWorkletNode | null>(null);
  const gain = useRef<GainNode | null>(null);
  const buffer = useRef<AudioChunkBuffer | null>(null);
  const pacer = useRef<AudioRequestPacer | null>(null);
  const index = useRef(0);
  const generation = useRef(0);
  const queue = useRef<Promise<void>>(Promise.resolve());
  const queuedChunks = useRef(0);
  const failure = useRef<Error | null>(null);

  const prepare = useCallback(async () => {
    const captureGeneration = generation.current;
    if (!navigator.mediaDevices?.getUserMedia) throw new Error('Microphone capture requires HTTPS (or localhost).');
    // Resume in the user's click handler before waiting for model initialization.
    const ctx = new AudioContext();
    context.current = ctx;
    await ctx.resume();
    if (captureGeneration !== generation.current) return false;
    const mic = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
    if (captureGeneration !== generation.current) {
      mic.getTracks().forEach((track) => track.stop());
      return false;
    }
    stream.current = mic;
    return true;
  }, []);

  const release = useCallback(() => {
    if (worklet.current) worklet.current.port.onmessage = null;
    source.current?.disconnect();
    worklet.current?.disconnect();
    gain.current?.disconnect();
    stream.current?.getTracks().forEach((track) => { track.onended = null; track.stop(); });
    stream.current = null;
    if (context.current) void context.current.close();
    context.current = null;
    source.current = null;
    worklet.current = null;
    gain.current = null;
    buffer.current = null;
  }, []);

  const stop = useCallback(() => {
    generation.current += 1;
    release();
    setIsRecording(false);
    setAudioLevel(0);
  }, [release]);

  const enqueue = useCallback((pcm: Float32Array, sampleRate: number, capturedAtMs: number, finalChunk = false) => {
    if (queuedChunks.current >= MAX_QUEUED_CHUNKS) {
      failure.current = new Error('Captioning is falling behind. Please stop and try again.');
      callbacks.current.onError(failure.current.message);
      return;
    }
    const chunkIndex = index.current++;
    const captureGeneration = generation.current;
    const requestPacer = pacer.current;
    const wav = encodeMonoPcm16Wav(downsampleTo16k(pcm, sampleRate), TARGET_SAMPLE_RATE);
    setChunkCount(index.current);
    queuedChunks.current += 1;
    // Keep one acknowledged request in flight and a bounded queue behind it.
    queue.current = queue.current.then(async () => {
      if (captureGeneration !== generation.current) return;
      // A final partial segment may use the one reserved request at stop.
      if (!finalChunk) await requestPacer?.wait();
      if (captureGeneration !== generation.current) return;
      requestPacer?.markSent();
      await callbacks.current.onChunk({ chunkIndex, audio: wav, capturedAtMs, mime: 'audio/wav', blobSizeBytes: wav.size });
    }).catch((error: unknown) => {
      if (captureGeneration !== generation.current) return;
      failure.current = error instanceof Error ? error : new Error('Unable to send audio.');
      callbacks.current.onError(failure.current.message);
    }).finally(() => { if (captureGeneration === generation.current) queuedChunks.current -= 1; });
  }, []);

  const flushAndStop = useCallback(async () => {
    // Preserve the last partial chunk, then wait for all caption acknowledgements.
    const remaining = buffer.current?.flush();
    if (context.current && remaining) {
      enqueue(remaining.samples, context.current.sampleRate, remaining.capturedAtMs, true);
    }
    release();
    setIsRecording(false);
    setAudioLevel(0);
    await queue.current;
    if (failure.current) throw failure.current;
  }, [enqueue, release]);

  const start = useCallback(async () => {
    const captureGeneration = ++generation.current;
    queue.current = Promise.resolve();
    queuedChunks.current = 0;
    failure.current = null;
    index.current = 0;
    pacer.current = new AudioRequestPacer(minRequestIntervalMs);
    setChunkCount(0);
    try {
      if (!navigator.mediaDevices?.getUserMedia) throw new Error('Microphone capture requires a supported browser and HTTPS (or localhost).');
      const mic = stream.current ?? await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
      if (captureGeneration !== generation.current) {
        mic.getTracks().forEach((track) => track.stop());
        return;
      }
      stream.current = mic;
      const ctx = context.current ?? new AudioContext();
      context.current = ctx;
      await ctx.resume();
      await ctx.audioWorklet.addModule('/audio/pcm-capture-worklet.js');
      if (captureGeneration !== generation.current) return;
      source.current = ctx.createMediaStreamSource(mic);
      const node = new AudioWorkletNode(ctx, 'pcm-capture-processor');
      worklet.current = node;
      gain.current = ctx.createGain();
      gain.current.gain.value = 0;
      source.current.connect(node);
      node.connect(gain.current);
      gain.current.connect(ctx.destination);
      buffer.current = new AudioChunkBuffer(ctx.sampleRate, chunkDurationMs, initialChunkDurationMs);
      let lastMeterUpdate = 0;
      node.port.onmessage = (event: MessageEvent<Float32Array[]>) => {
        if (captureGeneration !== generation.current) return;
        const mono = downmixChannelsToMono(event.data);
        if (performance.now() - lastMeterUpdate > 80) {
          setAudioLevel(computeAudioLevel(mono));
          lastMeterUpdate = performance.now();
        }
        for (const segment of buffer.current!.push(mono, performance.now())) {
          enqueue(segment.samples, ctx.sampleRate, segment.capturedAtMs);
        }
      };
      mic.getAudioTracks().forEach((track) => {
        track.onended = () => callbacks.current.onError('Microphone recording was interrupted.');
      });
      setIsRecording(true);
    } catch (error) {
      if (captureGeneration !== generation.current) return;
      stop();
      throw error;
    }
  }, [chunkDurationMs, initialChunkDurationMs, minRequestIntervalMs, enqueue, stop]);

  useEffect(() => () => { generation.current += 1; release(); }, [release]);
  return { isRecording, audioLevel, chunkCount, prepare, start, stop, flushAndStop };
}
