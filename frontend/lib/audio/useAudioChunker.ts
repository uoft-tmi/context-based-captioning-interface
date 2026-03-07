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

function getSupportedMime(preferredMimeType: ChunkerMime): ChunkerMime {
  if (typeof MediaRecorder === "undefined") {
    return preferredMimeType;
  }

  if (MediaRecorder.isTypeSupported(preferredMimeType)) {
    return preferredMimeType;
  }

  return "audio/webm";
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
  } = options;

  const [isRecording, setIsRecording] = useState(false);
  const [permissionStatus, setPermissionStatus] = useState<PermissionStatus>("idle");
  const [chunkCount, setChunkCount] = useState(0);
  const [lastChunkSizeBytes, setLastChunkSizeBytes] = useState<number | null>(null);

  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunkIndexRef = useRef(0);
  const sessionStartedAtRef = useRef<number | null>(null);
  const lastChunkAtRef = useRef<number | null>(null);
  const stopRequestedRef = useRef(false);

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
      const message =
        error instanceof DOMException && error.name === "NotAllowedError"
          ? "Microphone permission was denied."
          : "Unable to access microphone.";

      setPermissionStatus(error instanceof DOMException && error.name === "NotAllowedError" ? "denied" : "error");
      onError?.(message);
      return false;
    }
  }, [cleanUpStream, onError]);

  const stop = useCallback(() => {
    stopRequestedRef.current = true;

    if (recorderRef.current && recorderRef.current.state !== "inactive") {
      recorderRef.current.stop();
    }

    recorderRef.current = null;
    setIsRecording(false);
    cleanUpStream();
  }, [cleanUpStream]);

  const start = useCallback(async () => {
    if (isRecording) {
      return;
    }

    const hasPermission =
      permissionStatus === "granted" || (await requestPermission());

    if (!hasPermission || !streamRef.current) {
      return;
    }

    if (typeof MediaRecorder === "undefined") {
      onError?.("MediaRecorder is not available in this browser.");
      return;
    }

    chunkIndexRef.current = 0;
    sessionStartedAtRef.current = null;
    lastChunkAtRef.current = null;
    setChunkCount(0);
    setLastChunkSizeBytes(null);
    stopRequestedRef.current = false;

    const supportedMime = getSupportedMime(preferredMimeType);
    let recorder: MediaRecorder;

    try {
      recorder = new MediaRecorder(streamRef.current, {
        mimeType: supportedMime,
        audioBitsPerSecond: 128_000,
      });
    } catch {
      onWarning?.(
        `Preferred recording format (${supportedMime}) is unavailable. Falling back to browser default.`
      );
      recorder = new MediaRecorder(streamRef.current);
    }

    recorder.ondataavailable = async (event: BlobEvent) => {
      if (!event.data || event.data.size === 0) {
        return;
      }

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
      setLastChunkSizeBytes(event.data.size);

      if (event.data.size > oversizedChunkWarningBytes) {
        onWarning?.(
          `Chunk ${chunkIndex} is large (${Math.round(
            event.data.size / 1024
          )} KB) and may increase latency.`
        );
      }

      try {
        const audioB64 = await blobToBase64(event.data);

        await onChunk({
          chunkIndex,
          audioB64,
          mime: supportedMime,
          blobSizeBytes: event.data.size,
          elapsedMs,
          driftMs,
          createdAt: new Date(now).toISOString(),
        });
      } catch (error) {
        const message =
          error instanceof Error
            ? error.message
            : `Failed to process chunk ${chunkIndex}.`;
        onError?.(message);
      }
    };

    recorder.onerror = () => {
      onError?.("Microphone recording failed.");
      stop();
    };

    recorder.onstop = () => {
      setIsRecording(false);
      cleanUpStream();

      if (!stopRequestedRef.current) {
        onWarning?.("Recording stopped unexpectedly. Please start again.");
      }
    };

    recorderRef.current = recorder;
    recorder.start(chunkDurationMs);
    setIsRecording(true);
  }, [
    chunkDurationMs,
    isRecording,
    onChunk,
    onError,
    onWarning,
    oversizedChunkWarningBytes,
    permissionStatus,
    preferredMimeType,
    requestPermission,
    stop,
    cleanUpStream,
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
