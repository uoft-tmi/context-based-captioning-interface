'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import {
  downloadSessionPdf,
  endSession,
  getSessionStreamUrlsWithAuth,
  markSessionError,
  type StreamServerMessage,
} from '@/lib/api';
import { useAudioChunker, type AudioChunk } from '@/lib/audio/useAudioChunker';

type LiveState =
  | 'CONNECTING'
  | 'STREAMING'
  | 'FINALIZING'
  | 'COMPLETE'
  | 'ERROR';

const WEBSOCKET_CONNECT_TIMEOUT_MS = 10_000;

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Unknown error';
}

function parseStreamMessage(raw: string): StreamServerMessage {
  try {
    const parsed = JSON.parse(raw) as StreamServerMessage & {
      type?: string;
      text?: string;
    };

    if (parsed.type === 'error') {
      return {
        ...parsed,
        error: parsed.error ?? parsed.text,
      };
    }

    if (parsed.type === 'final') {
      return {
        ...parsed,
        final_text: parsed.final_text ?? parsed.text,
        is_final: true,
      };
    }

    if (parsed.type === 'caption') {
      return {
        ...parsed,
        partial_text: parsed.partial_text ?? parsed.text,
      };
    }

    return parsed;
  } catch {
    return { partial_text: raw };
  }
}

function base64ToBytes(base64: string): Uint8Array {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);

  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }

  return bytes;
}

export default function LiveSessionPage() {
  const searchParams = useSearchParams();
  const sessionId = searchParams.get('sessionId');
  const mode = searchParams.get('mode') ?? 'baseline';

  const [liveState, setLiveState] = useState<LiveState>('CONNECTING');
  const [statusMsg, setStatusMsg] = useState('Preparing recording...');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [liveCaption, setLiveCaption] = useState('');
  const [finalCaptions, setFinalCaptions] = useState<string[]>([]);
  const [isDownloading, setIsDownloading] = useState(false);

  const mountedRef = useRef(true);
  const socketRef = useRef<WebSocket | null>(null);
  const lifecycleRef = useRef<'idle' | 'ending' | 'ended' | 'errored'>('idle');
  const finalizePendingRef = useRef(false);
  const manualSocketCloseRef = useRef(false);
  const downloadUrlRef = useRef<string | null>(null);
  const failureHandlerRef = useRef<(reason: string, details?: string) => void>(
    () => {
      // Assigned by effect.
    },
  );

  const closeStreamingSocket = useCallback((code: number, reason: string) => {
    const ws = socketRef.current;
    if (!ws) {
      return;
    }

    ws.onopen = null;
    ws.onmessage = null;
    ws.onerror = null;
    ws.onclose = null;

    if (
      ws.readyState === WebSocket.OPEN ||
      ws.readyState === WebSocket.CONNECTING
    ) {
      try {
        ws.close(code, reason);
      } catch {
        // Ignore socket close errors during teardown.
      }
    }

    socketRef.current = null;
  }, []);

  const sendAudioChunk = useCallback(
    async (chunk: AudioChunk): Promise<void> => {
      const ws = socketRef.current;
      if (!ws || ws.readyState !== WebSocket.OPEN) {
        throw new Error('Streaming connection is not open.');
      }

      ws.send(base64ToBytes(chunk.audioB64));
    },
    [],
  );

  const {
    isRecording,
    audioLevel,
    permissionStatus,
    chunkCount,
    lastChunkSizeBytes,
    requestPermission,
    start,
    stop,
  } = useAudioChunker({
    onChunk: sendAudioChunk,
    onWarning: (message) => {
      setStatusMsg(message);
      if (message.toLowerCase().includes('dropped')) {
        failureHandlerRef.current(
          'Audio chunk streaming was interrupted.',
          message,
        );
      }
    },
    onError: (message) => {
      failureHandlerRef.current('Audio capture failed.', message);
    },
    chunkDurationMs: 2500,
  });

  const requestPermissionRef = useRef(requestPermission);
  const startRef = useRef(start);

  useEffect(() => {
    requestPermissionRef.current = requestPermission;
  }, [requestPermission]);

  useEffect(() => {
    startRef.current = start;
  }, [start]);

  const finalizeAsError = useCallback(
    async (reason: string, details?: string) => {
      if (!sessionId) {
        setErrorMsg(`${reason}${details ? ` ${details}` : ''}`);
        setLiveState('ERROR');
        return;
      }

      if (finalizePendingRef.current || lifecycleRef.current !== 'idle') {
        if (lifecycleRef.current === 'errored') {
          setLiveState('ERROR');
        }
        return;
      }

      finalizePendingRef.current = true;
      lifecycleRef.current = 'errored';
      manualSocketCloseRef.current = true;
      setErrorMsg(`${reason}${details ? ` ${details}` : ''}`);
      setStatusMsg('Marking session as failed...');
      setLiveState('FINALIZING');

      stop();
      closeStreamingSocket(4000, 'session_error');

      try {
        await markSessionError(sessionId, {
          reason,
          details,
          source: 'frontend-live-page',
        });
      } catch (error) {
        console.error('Failed to mark session as error:', error);
      } finally {
        finalizePendingRef.current = false;
        if (!mountedRef.current) {
          return;
        }
        setLiveState('ERROR');
      }
    },
    [closeStreamingSocket, sessionId, stop],
  );

  const finalizeAsEnded = useCallback(async () => {
    if (!sessionId) {
      return;
    }

    if (finalizePendingRef.current || lifecycleRef.current === 'ended') {
      return;
    }

    if (lifecycleRef.current === 'errored') {
      setLiveState('ERROR');
      return;
    }

    finalizePendingRef.current = true;
    lifecycleRef.current = 'ending';
    manualSocketCloseRef.current = true;
    setStatusMsg('Ending session...');
    setLiveState('FINALIZING');

    stop();
    closeStreamingSocket(1000, 'session_end');

    try {
      await endSession(sessionId);
      lifecycleRef.current = 'ended';

      if (!mountedRef.current) {
        return;
      }

      setStatusMsg('Session ended successfully.');
      setLiveState('COMPLETE');
    } catch (error) {
      const message = getErrorMessage(error);
      lifecycleRef.current = 'errored';
      setErrorMsg(`Failed to end session gracefully. ${message}`);
      setLiveState('ERROR');
    } finally {
      finalizePendingRef.current = false;
    }
  }, [closeStreamingSocket, sessionId, stop]);

  const handleUnexpectedFailure = useCallback(
    (reason: string, details?: string) => {
      if (lifecycleRef.current !== 'idle') {
        return;
      }
      void finalizeAsError(reason, details);
    },
    [finalizeAsError],
  );

  useEffect(() => {
    failureHandlerRef.current = handleUnexpectedFailure;
  }, [handleUnexpectedFailure]);

  const connectSocket = useCallback(
    async (streamUrl: string): Promise<WebSocket> => {
      return new Promise<WebSocket>((resolve, reject) => {
        const ws = new WebSocket(streamUrl);
        let settled = false;

        const timeout = window.setTimeout(() => {
          if (settled) {
            return;
          }
          settled = true;
          try {
            ws.close(4001, 'connect_timeout');
          } catch {
            // Ignore close errors during timeout path.
          }
          reject(
            new Error('Timed out connecting to the transcription stream.'),
          );
        }, WEBSOCKET_CONNECT_TIMEOUT_MS);

        ws.onopen = () => {
          if (settled) {
            return;
          }
          settled = true;
          window.clearTimeout(timeout);
          resolve(ws);
        };

        ws.onerror = () => {
          if (settled) {
            return;
          }
          // Let onclose provide a richer code/reason when available.
        };

        ws.onclose = (event) => {
          if (settled) {
            return;
          }
          settled = true;
          window.clearTimeout(timeout);
          reject(
            new Error(
              `WebSocket closed before opening (${streamUrl}) code ${event.code}${
                event.reason ? `: ${event.reason}` : ''
              }`,
            ),
          );
        };
      });
    },
    [],
  );

  const handleDownloadPdf = useCallback(async () => {
    if (!sessionId) {
      return;
    }

    setIsDownloading(true);

    try {
      const blob = await downloadSessionPdf(sessionId);
      const objectUrl = URL.createObjectURL(blob);

      if (downloadUrlRef.current) {
        URL.revokeObjectURL(downloadUrlRef.current);
      }
      downloadUrlRef.current = objectUrl;

      const anchor = document.createElement('a');
      anchor.href = objectUrl;
      anchor.download = `session-${sessionId}.pdf`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
    } catch (error) {
      setErrorMsg(`Failed to download session PDF. ${getErrorMessage(error)}`);
    } finally {
      setIsDownloading(false);
    }
  }, [sessionId]);

  useEffect(() => {
    if (!sessionId) {
      setErrorMsg('Missing session id. Start a new session first.');
      setLiveState('ERROR');
      return;
    }

    let cancelled = false;

    const startLiveStream = async () => {
      setStatusMsg('Requesting microphone permission...');

      try {
        const permissionGranted = await requestPermissionRef.current();
        if (!permissionGranted) {
          throw new Error(
            'Microphone permission was denied or no microphone was detected.',
          );
        }

        setStatusMsg('Connecting to live transcription stream...');

        const streamUrls = await getSessionStreamUrlsWithAuth(sessionId);
        let ws: WebSocket | null = null;
        const connectFailures: string[] = [];

        for (const streamUrl of streamUrls) {
          try {
            ws = await connectSocket(streamUrl);
            break;
          } catch (connectError) {
            connectFailures.push(getErrorMessage(connectError));
          }
        }

        if (!ws) {
          throw new Error(
            `WebSocket connection failed. ${connectFailures.join(' | ')}`,
          );
        }

        if (cancelled) {
          ws.close(1000, 'cancelled_before_start');
          return;
        }

        socketRef.current = ws;
        manualSocketCloseRef.current = false;

        ws.onmessage = (event: MessageEvent) => {
          if (typeof event.data !== 'string') {
            return;
          }

          const message = parseStreamMessage(event.data);

          if (message.error || message.detail) {
            handleUnexpectedFailure(
              'Backend stream reported an error.',
              message.error ?? message.detail,
            );
            return;
          }

          const incomingText =
            message.final_text ??
            message.partial_text ??
            message.text ??
            message.caption;

          if (incomingText && incomingText.trim().length > 0) {
            if (message.is_final || message.final_text) {
              setFinalCaptions((prev) => [...prev, incomingText]);
              setLiveCaption('');
            } else {
              setLiveCaption(incomingText);
            }
          }

          if (message.done) {
            void finalizeAsEnded();
          }
        };

        ws.onerror = () => {
          handleUnexpectedFailure('Streaming connection encountered an error.');
        };

        ws.onclose = (event) => {
          socketRef.current = null;

          if (manualSocketCloseRef.current || lifecycleRef.current !== 'idle') {
            return;
          }

          handleUnexpectedFailure(
            'Streaming connection was interrupted.',
            `Close code ${event.code}${event.reason ? `: ${event.reason}` : ''}`,
          );
        };

        setStatusMsg('Starting microphone capture...');
        await startRef.current();

        if (!cancelled && lifecycleRef.current === 'idle') {
          setLiveState('STREAMING');
          setStatusMsg('Recording in progress.');
        }
      } catch (error) {
        handleUnexpectedFailure(
          'Unable to start recording.',
          getErrorMessage(error),
        );
      }
    };

    void startLiveStream();

    return () => {
      cancelled = true;
    };
  }, [connectSocket, finalizeAsEnded, handleUnexpectedFailure, sessionId]);

  useEffect(() => {
    mountedRef.current = true;

    return () => {
      mountedRef.current = false;
      manualSocketCloseRef.current = true;
      closeStreamingSocket(1001, 'component_unmount');
      stop();

      if (sessionId && lifecycleRef.current === 'idle') {
        lifecycleRef.current = 'errored';
        void markSessionError(sessionId, {
          reason: 'component_unmounted',
          details: 'Live recording page unmounted before session finalization.',
          source: 'frontend-live-page',
        }).catch((error) => {
          console.error('Failed to mark session error on unmount:', error);
        });
      }

      if (downloadUrlRef.current) {
        URL.revokeObjectURL(downloadUrlRef.current);
        downloadUrlRef.current = null;
      }
    };
  }, [closeStreamingSocket, sessionId, stop]);

  useEffect(() => {
    const handleOffline = () => {
      if (sessionId && lifecycleRef.current === 'idle') {
        handleUnexpectedFailure(
          'Network connection dropped.',
          'Browser is offline.',
        );
      }
    };

    window.addEventListener('offline', handleOffline);
    return () => window.removeEventListener('offline', handleOffline);
  }, [handleUnexpectedFailure, sessionId]);

  const pulseTransform = `scale(${1 + Math.min(audioLevel, 1) * 0.9})`;
  const pulseGlow = `${20 + Math.round(audioLevel * 50)}px`;

  return (
    <div className='glass-panel w-full max-w-3xl p-8 sm:p-12 space-y-8 relative overflow-hidden'>
      <div className='absolute top-0 right-0 -mr-12 -mt-12 w-48 h-48 rounded-full bg-(--brand) opacity-5 blur-3xl'></div>
      <div className='absolute bottom-0 left-0 -ml-12 -mb-12 w-48 h-48 rounded-full bg-(--brand-accent) opacity-5 blur-3xl'></div>

      <div className='relative z-10 w-full space-y-6'>
        <div className='text-center'>
          <h2 className='text-2xl font-bold text-foreground'>
            Live Audio Session
          </h2>
          <p className='text-(--text-secondary)'>
            {mode === 'context'
              ? 'Context mode with uploaded notes.'
              : 'Baseline mode.'}
          </p>
          <p className='text-sm text-(--text-secondary)'>{statusMsg}</p>
        </div>

        {(liveState === 'CONNECTING' ||
          liveState === 'STREAMING' ||
          liveState === 'FINALIZING') && (
          <>
            <div className='text-center'>
              <p className='text-sm text-(--text-secondary)'>
                Chunk {chunkCount} | Mic: {permissionStatus}
              </p>
            </div>

            <div className='flex justify-center'>
              <div className='relative h-48 w-48 flex items-center justify-center'>
                <div className='absolute inset-0 rounded-full border border-(--brand) opacity-20 animate-ping'></div>
                <div
                  className='h-28 w-28 rounded-full bg-(--brand) transition-all duration-100 ease-out'
                  style={{
                    transform: pulseTransform,
                    boxShadow: `0 0 ${pulseGlow} rgba(59,130,246,0.65)`,
                  }}
                />
                <div className='absolute text-(--brand-text) font-semibold text-sm'>
                  REC
                </div>
              </div>
            </div>

            <div className='grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm'>
              <div className='rounded-xl border border-(--input-border) bg-(--input-bg) p-3 text-center'>
                <p className='text-(--text-secondary)'>Audio Level</p>
                <p className='font-semibold text-lg'>
                  {Math.round(audioLevel * 100)}%
                </p>
              </div>
              <div className='rounded-xl border border-(--input-border) bg-(--input-bg) p-3 text-center'>
                <p className='text-(--text-secondary)'>Last Chunk Size</p>
                <p className='font-semibold text-lg'>
                  {lastChunkSizeBytes
                    ? `${Math.round(lastChunkSizeBytes / 1024)} KB`
                    : '-'}
                </p>
              </div>
            </div>

            <div className='rounded-2xl border border-(--input-border) bg-(--input-bg) p-4 space-y-4'>
              <div>
                <p className='text-xs uppercase tracking-wide text-(--text-secondary) mb-1'>
                  Live Caption
                </p>
                <p className='min-h-10 text-foreground'>
                  {liveCaption || 'Listening...'}
                </p>
              </div>

              <div>
                <p className='text-xs uppercase tracking-wide text-(--text-secondary) mb-1'>
                  Transcript
                </p>
                <div className='max-h-56 overflow-y-auto rounded-xl border border-(--input-border) bg-white/60 dark:bg-slate-900/30 p-3 space-y-2'>
                  {finalCaptions.length === 0 && (
                    <p className='text-sm text-(--text-secondary)'>
                      No finalized lines yet.
                    </p>
                  )}
                  {finalCaptions.map((caption, index) => (
                    <p
                      key={`${index}-${caption.slice(0, 12)}`}
                      className='text-sm text-foreground'
                    >
                      {caption}
                    </p>
                  ))}
                </div>
              </div>
            </div>

            <div className='flex justify-center'>
              <button
                onClick={() => {
                  void finalizeAsEnded();
                }}
                disabled={finalizePendingRef.current || !isRecording}
                className='px-8 py-3 bg-red-600 text-white font-bold rounded-full shadow hover:bg-red-700 transition-colors disabled:opacity-60 disabled:cursor-not-allowed'
              >
                Stop Recording
              </button>
            </div>
          </>
        )}

        {liveState === 'COMPLETE' && (
          <>
            <div className='text-center'>
              <h3 className='text-xl font-bold text-foreground'>
                Session Complete
              </h3>
              <p className='text-(--text-secondary)'>
                Recording stopped and session ended cleanly.
              </p>
            </div>
            <div className='flex flex-wrap gap-3 justify-center'>
              <button
                onClick={() => {
                  void handleDownloadPdf();
                }}
                disabled={isDownloading}
                className='px-6 py-2 bg-(--brand) text-(--brand-text) font-semibold rounded-full shadow hover:bg-(--brand-accent) transition-colors disabled:opacity-60'
              >
                {isDownloading ? 'Downloading...' : 'Download Session PDF'}
              </button>
              <button
                onClick={() => {
                  if (typeof window !== 'undefined') {
                    window.location.replace('/session');
                  }
                }}
                className='px-6 py-2 border border-(--input-border) rounded-full hover:bg-(--card-bg) transition-colors'
              >
                Back to Session
              </button>
            </div>
          </>
        )}

        {liveState === 'ERROR' && (
          <div className='space-y-6 text-center text-red-600'>
            <h3 className='text-xl font-bold'>Error</h3>
            <p className='text-sm bg-red-50 p-4 rounded-xl border border-red-200'>
              {errorMsg || 'An unknown error occurred.'}
            </p>
            <button
              onClick={() => {
                if (typeof window !== 'undefined') {
                  window.location.replace('/session');
                }
              }}
              className='px-8 py-3 bg-red-600 text-white font-bold rounded-full shadow hover:bg-red-700 transition-colors mt-2 mx-auto block'
            >
              Back to Session
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
