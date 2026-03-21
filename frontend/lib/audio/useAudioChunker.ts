"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Audio chunk MIME type.
 * - "audio/webm": Most browser support, smaller size
 * - "audio/wav": Lossless, larger size
 */
export type ChunkerMime = "audio/webm" | "audio/wav";

type PermissionStatus = "idle" | "granted" | "denied" | "error";

export interface AudioChunk {
  chunkIndex: number;
  audioB64: string;
  mime: ChunkerMime;
  blobSizeBytes: number;
  elapsedMs: number;
  driftMs: number;
  createdAt: string;
}

interface UseAudioChunkerOptions {
  onChunk: (chunk: AudioChunk) => Promise<void> | void;
  onWarning?: (message: string) => void;
  onError?: (message: string) => void;
  chunkDurationMs?: number;
  preferredMimeType?: ChunkerMime;
  oversizedChunkWarningBytes?: number;
  chunkFailureRetryCount?: number;
  chunkFailureRetryDelayMs?: number;
}

interface UseAudioChunkerResult {
  isRecording: boolean;
  permissionStatus: PermissionStatus;
  chunkCount: number;
  lastChunkSizeBytes: number | null;
  requestPermission: () => Promise<boolean>;
  start: () => Promise<void>;
  stop: () => void;
}

const DEFAULT_CHUNK_DURATION_MS = 3000;
const DEFAULT_OVERSIZED_WARNING_BYTES = 512 * 1024;
const DEFAULT_CHUNK_FAILURE_RETRY_COUNT = 1;
const DEFAULT_CHUNK_FAILURE_RETRY_DELAY_MS = 300;
const TARGET_SAMPLE_RATE = 16_000;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();

    reader.onloadend = () => {
      const result = reader.result;
      if (typeof result !== "string") {
        reject(new Error("Failed to encode audio chunk as base64"));
        return;
      }

      const base64 = result.split(",")[1];
      if (!base64) {
        reject(new Error("Missing base64 payload from audio chunk"));
        return;
      }

      resolve(base64);
    };

    reader.onerror = () => reject(new Error("Unable to read audio chunk"));
    reader.readAsDataURL(blob);
  });
}

function downsampleTo16k(input: Float32Array, sourceRate: number): Float32Array {
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

  writeString(0, "RIFF");
  view.setUint32(4, 36 + dataSize, true);
  writeString(8, "WAVE");
  writeString(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, byteRate, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, 16, true);
  writeString(36, "data");
  view.setUint32(40, dataSize, true);

  let offset = 44;
  for (let i = 0; i < samples.length; i += 1) {
    const sample = Math.max(-1, Math.min(1, samples[i]));
    const int16 = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
    view.setInt16(offset, int16, true);
    offset += bytesPerSample;
  }

  return new Blob([buffer], { type: "audio/wav" });
}

function consumeSamples(queue: Float32Array[], sampleCount: number): Float32Array {
  const out = new Float32Array(sampleCount);
  let offset = 0;

  while (offset < sampleCount && queue.length > 0) {
    const head = queue[0];
    const needed = sampleCount - offset;

    if (head.length <= needed) {
      out.set(head, offset);
      offset += head.length;
      queue.shift();
      continue;
    }

    out.set(head.subarray(0, needed), offset);
    queue[0] = head.subarray(needed);
    offset += needed;
  }

  return out;
}

export function useAudioChunker(options: UseAudioChunkerOptions): UseAudioChunkerResult {
  /**
   * Custom hook for microphone audio capture and chunking.
   *
   * Usage:
   * ```
   * const { isRecording, permissionStatus, start, stop, requestPermission } = useAudioChunker({
   *   onChunk: async (chunk) => {
   *     console.log(`Chunk ${chunk.chunkIndex}: ${chunk.blobSizeBytes} bytes, drift ${chunk.driftMs}ms`);
   *     // Send chunk to backend: await sendChunk(sessionId, chunk);
   *   },
   *   chunkDurationMs: 3000,
   *   onWarning: (msg) => console.warn(msg),
   *   onError: (msg) => console.error(msg),
   * });
   *
   * // Request permission first
   * await requestPermission();
   *
   * // Start recording (emits chunks every 3 seconds)
   * await start();
   *
   * // Stop recording
   * stop();
   * ```
   *
   * Options:
   * - onChunk: Called for each captured chunk (required).
   * - chunkDurationMs: Chunk interval in ms (default 3000).
   * - preferredMimeType: "audio/webm" or "audio/wav" (default "audio/webm").
   * - onWarning, onError: Optional logging callbacks.
   *
   * Returns:
   * - isRecording: True if currently recording.
   * - permissionStatus: "idle" | "granted" | "denied" | "error".
   * - chunkCount: Number of chunks captured so far.
   * - lastChunkSizeBytes: Size of most recent chunk in bytes.
   * - requestPermission() / start() / stop(): Control recording.
   */
  const {
    onChunk,
    onWarning,
    onError,
    chunkDurationMs = DEFAULT_CHUNK_DURATION_MS,
    preferredMimeType = "audio/webm",
    oversizedChunkWarningBytes = DEFAULT_OVERSIZED_WARNING_BYTES,
    chunkFailureRetryCount = DEFAULT_CHUNK_FAILURE_RETRY_COUNT,
    chunkFailureRetryDelayMs = DEFAULT_CHUNK_FAILURE_RETRY_DELAY_MS,
  } = options;

  const [isRecording, setIsRecording] = useState(false);
  const [permissionStatus, setPermissionStatus] = useState<PermissionStatus>("idle");
  const [chunkCount, setChunkCount] = useState(0);
  const [lastChunkSizeBytes, setLastChunkSizeBytes] = useState<number | null>(null);

  const streamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const sourceNodeRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const processorNodeRef = useRef<ScriptProcessorNode | null>(null);
  const mutedGainNodeRef = useRef<GainNode | null>(null);
  const pcmQueueRef = useRef<Float32Array[]>([]);
  const queuedSampleCountRef = useRef(0);
  const chunkIndexRef = useRef(0);
  const sessionStartedAtRef = useRef<number | null>(null);
  const lastChunkAtRef = useRef<number | null>(null);
  const stopRequestedRef = useRef(false);

  const cleanUpAudioGraph = useCallback(() => {
    processorNodeRef.current?.disconnect();
    sourceNodeRef.current?.disconnect();
    mutedGainNodeRef.current?.disconnect();

    processorNodeRef.current = null;
    sourceNodeRef.current = null;
    mutedGainNodeRef.current = null;

    const ctx = audioContextRef.current;
    audioContextRef.current = null;
    if (ctx) {
      void ctx.close();
    }

    pcmQueueRef.current = [];
    queuedSampleCountRef.current = 0;
  }, []);

  const cleanUpStream = useCallback(() => {
    if (!streamRef.current) {
      return;
    }

    streamRef.current.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }, []);

  const requestPermission = useCallback(async (): Promise<boolean> => {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setPermissionStatus("error");
      onError?.("Microphone capture is not supported in this browser.");
      return false;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

      const hasAudioTrack = stream.getAudioTracks().length > 0;
      if (!hasAudioTrack) {
        stream.getTracks().forEach((track) => track.stop());
        setPermissionStatus("error");
        onError?.("No microphone input was detected.");
        return false;
      }

      cleanUpStream();
      streamRef.current = stream;
      setPermissionStatus("granted");
      return true;
    } catch (error) {
      let message = "Unable to access microphone.";
      let nextStatus: PermissionStatus = "error";

      if (error instanceof DOMException) {
        switch (error.name) {
          case "NotAllowedError":
            message = "Microphone permission was denied.";
            nextStatus = "denied";
            break;
          case "NotFoundError":
            message = "No microphone was found on this device.";
            break;
          case "NotReadableError":
            message = "Microphone is already in use by another application.";
            break;
          case "AbortError":
            message = "Microphone capture was interrupted. Please try again.";
            break;
          case "OverconstrainedError":
            message = "Microphone settings are unsupported on this device.";
            break;
          case "SecurityError":
            message = "Microphone access is blocked by browser security settings.";
            break;
          default:
            message = "Unable to access microphone.";
            break;
        }
      }

      setPermissionStatus(nextStatus);
      onError?.(message);
      return false;
    }
  }, [cleanUpStream, onError]);

  const stop = useCallback(() => {
    stopRequestedRef.current = true;

    setIsRecording(false);
    cleanUpAudioGraph();
    cleanUpStream();
  }, [cleanUpAudioGraph, cleanUpStream]);

  const start = useCallback(async () => {
    if (isRecording) {
      return;
    }

    const hasPermission =
      permissionStatus === "granted" || (await requestPermission());

    if (!hasPermission || !streamRef.current) {
      return;
    }

    const AudioCtx = window.AudioContext || (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!AudioCtx) {
      onError?.("Web Audio API is not available in this browser.");
      return;
    }

    chunkIndexRef.current = 0;
    sessionStartedAtRef.current = null;
    lastChunkAtRef.current = null;
    setChunkCount(0);
    setLastChunkSizeBytes(null);
    stopRequestedRef.current = false;

    if (preferredMimeType !== "audio/wav") {
      onWarning?.("Captured audio is always emitted as 16kHz mono WAV for backend compatibility.");
    }

    let audioContext: AudioContext;
    try {
      audioContext = new AudioCtx();
    } catch {
      onError?.("Failed to initialize audio processing. Please reload and try again.");
      return;
    }

    if (audioContext.state === "suspended") {
      try {
        await audioContext.resume();
      } catch {
        onError?.("Audio context is suspended. Interact with the page and try recording again.");
        void audioContext.close();
        return;
      }
    }

    const source = audioContext.createMediaStreamSource(streamRef.current);
    const processor = audioContext.createScriptProcessor(4096, 1, 1);
    const mutedGain = audioContext.createGain();
    mutedGain.gain.value = 0;

    source.connect(processor);
    processor.connect(mutedGain);
    mutedGain.connect(audioContext.destination);

    audioContextRef.current = audioContext;
    sourceNodeRef.current = source;
    processorNodeRef.current = processor;
    mutedGainNodeRef.current = mutedGain;

    const samplesPerChunk = Math.max(
      1,
      Math.round(audioContext.sampleRate * (chunkDurationMs / 1000))
    );

    processor.onaudioprocess = (event: AudioProcessingEvent) => {
      const input = event.inputBuffer.getChannelData(0);
      if (!input || input.length === 0) {
        return;
      }

      const copied = new Float32Array(input.length);
      copied.set(input);
      pcmQueueRef.current.push(copied);
      queuedSampleCountRef.current += copied.length;

      while (queuedSampleCountRef.current >= samplesPerChunk) {
        const chunkSamples = consumeSamples(pcmQueueRef.current, samplesPerChunk);
        queuedSampleCountRef.current -= samplesPerChunk;

        const downsampled = downsampleTo16k(chunkSamples, audioContext.sampleRate);
        const wavChunk = encodeMonoPcm16Wav(downsampled, TARGET_SAMPLE_RATE);

        const now = Date.now();
        if (sessionStartedAtRef.current === null) {
          sessionStartedAtRef.current = now;
        }

        const elapsedMs = now - sessionStartedAtRef.current;
        const driftMs =
          lastChunkAtRef.current === null
            ? 0
            : now - lastChunkAtRef.current - chunkDurationMs;
        lastChunkAtRef.current = now;

        const chunkIndex = chunkIndexRef.current;
        chunkIndexRef.current += 1;
        setChunkCount((prev) => prev + 1);
        setLastChunkSizeBytes(wavChunk.size);

        if (wavChunk.size > oversizedChunkWarningBytes) {
          onWarning?.(
            `Chunk ${chunkIndex} is large (${Math.round(
              wavChunk.size / 1024
            )} KB) and may increase latency.`
          );
        }

        void (async () => {
          try {
            const audioB64 = await blobToBase64(wavChunk);
            const chunkPayload: AudioChunk = {
              chunkIndex,
              audioB64,
              mime: "audio/wav",
              blobSizeBytes: wavChunk.size,
              elapsedMs,
              driftMs,
              createdAt: new Date(now).toISOString(),
            };

            let attempt = 0;
            const maxAttempts = Math.max(0, chunkFailureRetryCount) + 1;

            while (attempt < maxAttempts) {
              try {
                await onChunk(chunkPayload);
                break;
              } catch (sendError) {
                attempt += 1;

                if (attempt >= maxAttempts) {
                  throw sendError;
                }

                onWarning?.(
                  `Chunk ${chunkIndex} upload failed (attempt ${attempt}/${maxAttempts - 1}). Retrying...`
                );
                await sleep(Math.max(0, chunkFailureRetryDelayMs));
              }
            }
          } catch (error) {
            const message =
              error instanceof Error
                ? error.message
                : `Failed to process chunk ${chunkIndex}.`;
            onError?.(message);
          }
        })();
      }
    };

    streamRef.current.getAudioTracks().forEach((track) => {
      track.onended = () => {
        setIsRecording(false);
        cleanUpAudioGraph();
        cleanUpStream();
        if (!stopRequestedRef.current) {
          onWarning?.("Recording stopped unexpectedly. Please start again.");
        }
      };
    });

    setIsRecording(true);
  }, [
    cleanUpAudioGraph,
    chunkDurationMs,
    isRecording,
    onChunk,
    onError,
    onWarning,
    oversizedChunkWarningBytes,
    permissionStatus,
    preferredMimeType,
    requestPermission,
    cleanUpStream,
    chunkFailureRetryCount,
    chunkFailureRetryDelayMs,
  ]);

  useEffect(() => {
    return () => {
      stop();
    };
  }, [stop]);

  return {
    isRecording,
    permissionStatus,
    chunkCount,
    lastChunkSizeBytes,
    requestPermission,
    start,
    stop,
  };
}
