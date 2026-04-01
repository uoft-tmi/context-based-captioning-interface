'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import NotesUpload from '@/components/notes-upload';
import {
  createSession,
  downloadSessionPdf,
  endSession,
  getActiveSession,
  getSessionStreamUrlsWithAuth,
  markSessionError,
  type SessionMode,
  type StreamChunkPayload,
  type StreamServerMessage,
} from '@/lib/api';
import { useAudioChunker, type AudioChunk } from '@/lib/audio/useAudioChunker';

type SessionState =
  | 'INIT'
  | 'NOTES_REQUIRED'
  | 'READY'
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
    return JSON.parse(raw) as StreamServerMessage;
  } catch {
    return { partial_text: raw };
  }
}

function formatFailureMessage(reason: string, details?: string): string {
  return details ? `${reason} ${details}` : reason;
}

export default function SessionPage() {
  const [sessionState, setSessionState] = useState<SessionState>('INIT');
  const [mode, setMode] = useState<SessionMode | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [isStarting, setIsStarting] = useState(false);
  const [isDownloading, setIsDownloading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [liveCaption, setLiveCaption] = useState('');
  const [finalCaptions, setFinalCaptions] = useState<string[]>([]);

  const sessionIdRef = useRef<string | null>(null);
  const mountedRef = useRef(true);
  const socketRef = useRef<WebSocket | null>(null);
  const lifecycleRef = useRef<'idle' | 'ending' | 'ended' | 'errored'>('idle');
  const finalizePendingRef = useRef(false);
  const manualSocketCloseRef = useRef(false);
  const failureHandlerRef = useRef<(reason: string, details?: string) => void>(
    () => {
      // Assigned after callbacks are initialized.
    },
  );
  const downloadUrlRef = useRef<string | null>(null);

  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);

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
        // Ignore close exceptions during forced teardown.
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

      const payload: StreamChunkPayload = {
        type: 'audio_chunk',
        chunk_index: chunk.chunkIndex,
        audio_b64: chunk.audioB64,
        mime: chunk.mime,
        elapsed_ms: chunk.elapsedMs,
        created_at: chunk.createdAt,
      };

      ws.send(JSON.stringify(payload));
    },
    [],
  );

  const {
    isRecording,
    permissionStatus,
    chunkCount,
    lastChunkSizeBytes,
    requestPermission,
    start,
    stop,
  } = useAudioChunker({
    onChunk: sendAudioChunk,
    onWarning: (message: string) => {
      setStatusMsg(message);
      if (message.toLowerCase().includes('dropped')) {
        failureHandlerRef.current(
          'Audio chunk streaming was interrupted.',
          message,
        );
      }
    },
    onError: (message: string) => {
      failureHandlerRef.current('Audio capture failed.', message);
    },
    chunkDurationMs: 2500,
  });

  const resetToInit = useCallback(() => {
    manualSocketCloseRef.current = true;
    closeStreamingSocket(1000, 'session_reset');
    stop();

    lifecycleRef.current = 'idle';
    finalizePendingRef.current = false;

    if (downloadUrlRef.current) {
      URL.revokeObjectURL(downloadUrlRef.current);
      downloadUrlRef.current = null;
    }

    setMode(null);
    setSessionId(null);
    setSessionState('INIT');
    setErrorMsg(null);
    setStatusMsg(null);
    setIsStarting(false);
    setIsDownloading(false);
    setLiveCaption('');
    setFinalCaptions([]);
  }, [closeStreamingSocket, stop]);

  const finalizeAsError = useCallback(
    async (reason: string, details?: string) => {
      const currentSessionId = sessionIdRef.current;

      if (!currentSessionId) {
        setErrorMsg(formatFailureMessage(reason, details));
        setSessionState('ERROR');
        return;
      }

      if (finalizePendingRef.current || lifecycleRef.current !== 'idle') {
        setErrorMsg(formatFailureMessage(reason, details));
        if (lifecycleRef.current === 'errored') {
          setSessionState('ERROR');
        }
        return;
      }

      finalizePendingRef.current = true;
      lifecycleRef.current = 'errored';
      manualSocketCloseRef.current = true;
      setErrorMsg(formatFailureMessage(reason, details));
      setStatusMsg('Marking session as failed...');
      setSessionState('FINALIZING');

      stop();
      closeStreamingSocket(4000, 'session_error');

      try {
        await markSessionError(currentSessionId, {
          reason,
          details,
          source: 'frontend',
        });
      } catch (apiError) {
        console.error('Failed to mark session as error:', apiError);
      } finally {
        finalizePendingRef.current = false;
        if (!mountedRef.current) {
          return;
        }
        setSessionState('ERROR');
      }
    },
    [closeStreamingSocket, stop],
  );

  const finalizeAsEnded = useCallback(async () => {
    const currentSessionId = sessionIdRef.current;

    if (!currentSessionId) {
      resetToInit();
      return;
    }

    if (finalizePendingRef.current || lifecycleRef.current === 'ended') {
      return;
    }

    if (lifecycleRef.current === 'errored') {
      if (mountedRef.current) {
        setSessionState('ERROR');
      }
      return;
    }

    finalizePendingRef.current = true;
    lifecycleRef.current = 'ending';
    manualSocketCloseRef.current = true;
    setStatusMsg('Ending session...');
    setSessionState('FINALIZING');

    stop();
    closeStreamingSocket(1000, 'session_end');

    try {
      await endSession(currentSessionId);
      lifecycleRef.current = 'ended';

      if (!mountedRef.current) {
        return;
      }

      setStatusMsg('Session ended successfully.');
      setSessionState('COMPLETE');
    } catch (endError) {
      const message = getErrorMessage(endError);

      try {
        await markSessionError(currentSessionId, {
          reason: 'failed_to_end_session',
          details: message,
          source: 'frontend',
        });
      } catch (markError) {
        console.error('Failed to report end-session error:', markError);
      }

      lifecycleRef.current = 'errored';
      if (!mountedRef.current) {
        return;
      }

      setErrorMsg(`Failed to end session gracefully. ${message}`);
      setSessionState('ERROR');
    } finally {
      finalizePendingRef.current = false;
    }
  }, [closeStreamingSocket, resetToInit, stop]);

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
          settled = true;
          window.clearTimeout(timeout);
          reject(new Error('WebSocket failed while connecting.'));
        };

        ws.onclose = (event) => {
          if (settled) {
            return;
          }
          settled = true;
          window.clearTimeout(timeout);
          reject(
            new Error(
              `WebSocket closed before opening (code ${event.code}${
                event.reason ? `: ${event.reason}` : ''
              }).`,
            ),
          );
        };
      });
    },
    [],
  );

  const handleStartRecording = useCallback(async () => {
    const currentSessionId = sessionIdRef.current;
    if (!currentSessionId || mode === null) {
      return;
    }

    if (typeof window !== 'undefined') {
      const params = new URLSearchParams({
        sessionId: currentSessionId,
        mode,
      });
      window.location.assign(`/session/live?${params.toString()}`);
      return;
    }

    setErrorMsg(null);
    setStatusMsg('Requesting microphone permission...');
    setIsStarting(true);

    try {
      const permissionGranted = await requestPermission();
      if (!permissionGranted) {
        throw new Error(
          'Microphone permission was denied or no microphone was detected.',
        );
      }

      setStatusMsg('Connecting to live transcription stream...');
      const streamUrls = await getSessionStreamUrlsWithAuth(currentSessionId);
      let ws: WebSocket | null = null;
      let lastConnectError: unknown = null;

      for (const streamUrl of streamUrls) {
        try {
          ws = await connectSocket(streamUrl);
          break;
        } catch (connectError) {
          lastConnectError = connectError;
        }
      }

      if (!ws) {
        throw new Error(
          `WebSocket failed while connecting. ${getErrorMessage(lastConnectError)}`,
        );
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
      await start();
      if (lifecycleRef.current === 'idle') {
        setSessionState('STREAMING');
        setStatusMsg('Recording in progress.');
      }
    } catch (startError) {
      handleUnexpectedFailure(
        'Unable to start recording.',
        getErrorMessage(startError),
      );
    } finally {
      if (mountedRef.current) {
        setIsStarting(false);
      }
    }
  }, [
    connectSocket,
    finalizeAsEnded,
    handleUnexpectedFailure,
    mode,
    requestPermission,
    start,
  ]);

  const handleCreateSession = async (selectedMode: SessionMode) => {
    setErrorMsg(null);
    setStatusMsg('Creating session...');
    setIsCreating(true);

    try {
      const data = await createSession(selectedMode);

      setMode(selectedMode);
      setSessionId(data.session_id);
      lifecycleRef.current = 'idle';
      finalizePendingRef.current = false;
      manualSocketCloseRef.current = false;
      setLiveCaption('');
      setFinalCaptions([]);

      if (selectedMode === 'context') {
        setSessionState('NOTES_REQUIRED');
        setStatusMsg('Upload a PDF to continue.');
      } else {
        setSessionState('READY');
        setStatusMsg('Session is ready to start recording.');
      }
    } catch (createError) {
      console.error(createError);
      setErrorMsg(getErrorMessage(createError));
      setSessionState('ERROR');
    } finally {
      setIsCreating(false);
    }
  };

  const handleDownloadPdf = useCallback(async () => {
    const currentSessionId = sessionIdRef.current;
    if (!currentSessionId) {
      return;
    }

    setIsDownloading(true);
    setErrorMsg(null);

    try {
      const blob = await downloadSessionPdf(currentSessionId);
      const objectUrl = URL.createObjectURL(blob);

      if (downloadUrlRef.current) {
        URL.revokeObjectURL(downloadUrlRef.current);
      }
      downloadUrlRef.current = objectUrl;

      const anchor = document.createElement('a');
      anchor.href = objectUrl;
      anchor.download = `session-${currentSessionId}.pdf`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
    } catch (downloadError) {
      setErrorMsg(
        `Failed to download session PDF. ${getErrorMessage(downloadError)}`,
      );
    } finally {
      setIsDownloading(false);
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;

    return () => {
      mountedRef.current = false;
      manualSocketCloseRef.current = true;
      closeStreamingSocket(1001, 'component_unmount');
      stop();

      const currentSessionId = sessionIdRef.current;
      if (currentSessionId && lifecycleRef.current === 'idle') {
        lifecycleRef.current = 'errored';
        void markSessionError(currentSessionId, {
          reason: 'component_unmounted',
          details: 'Session page unmounted before the session was finalized.',
          source: 'frontend',
        }).catch((error) => {
          console.error('Failed to mark session error on unmount:', error);
        });
      }

      if (downloadUrlRef.current) {
        URL.revokeObjectURL(downloadUrlRef.current);
        downloadUrlRef.current = null;
      }
    };
  }, [closeStreamingSocket, stop]);

  useEffect(() => {
    const handleOffline = () => {
      if (sessionIdRef.current && lifecycleRef.current === 'idle') {
        handleUnexpectedFailure(
          'Network connection dropped.',
          'Browser is offline.',
        );
      }
    };

    window.addEventListener('offline', handleOffline);
    return () => window.removeEventListener('offline', handleOffline);
  }, [handleUnexpectedFailure]);

  useEffect(() => {
    let cancelled = false;

    const restoreActiveSession = async () => {
      try {
        const activeSession = await getActiveSession();
        if (cancelled || !activeSession?.session_id) {
          return;
        }

        const status = activeSession.status?.toLowerCase() ?? '';
        if (
          status === 'complete' ||
          status === 'completed' ||
          status === 'ended'
        ) {
          return;
        }

        setMode(activeSession.mode ?? 'baseline');
        setSessionId(activeSession.session_id);
        setSessionState('READY');
        setStatusMsg('Resumed existing active session.');
      } catch (restoreError) {
        console.warn('Unable to restore active session:', restoreError);
      }
    };

    void restoreActiveSession();

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className='glass-panel w-full max-w-2xl p-8 sm:p-12 space-y-8 relative overflow-hidden'>
      <div className='absolute top-0 right-0 -mr-12 -mt-12 w-48 h-48 rounded-full bg-(--brand) opacity-5 blur-3xl'></div>
      <div className='absolute bottom-0 left-0 -ml-12 -mb-12 w-48 h-48 rounded-full bg-(--brand-accent) opacity-5 blur-3xl'></div>

      <div className='relative z-10 w-full'>
        {sessionState === 'INIT' && (
          <div className='space-y-6 text-center'>
            <h2 className='text-2xl font-bold text-foreground'>New Session</h2>
            <p className='text-(--text-secondary)'>
              Select a captioning mode to begin. Baseline is standard
              transcription. Context mode uses uploaded notes to improve
              domain-specific accuracy.
            </p>

            <div className='grid grid-cols-1 md:grid-cols-2 gap-4 mt-8'>
              <button
                onClick={() => handleCreateSession('baseline')}
                disabled={isCreating}
                className='flex flex-col items-center justify-center p-6 border-2 border-(--input-border) rounded-2xl hover:border-(--brand) hover:shadow-md transition-all group bg-(--input-bg) disabled:opacity-50 disabled:cursor-not-allowed'
              >
                <div className='h-12 w-12 rounded-full bg-slate-100 flex items-center justify-center mb-4 group-hover:bg-blue-50 transition-colors'>
                  <span className='text-2xl'>A</span>
                </div>
                <h3 className='font-semibold text-lg'>Baseline</h3>
                <p className='text-sm text-(--text-secondary) mt-2'>
                  Standard AI captioning without extra context.
                </p>
              </button>

              <button
                onClick={() => handleCreateSession('context')}
                disabled={isCreating}
                className='flex flex-col items-center justify-center p-6 border-2 border-(--input-border) rounded-2xl hover:border-(--brand) hover:shadow-md transition-all group bg-(--input-bg) disabled:opacity-50 disabled:cursor-not-allowed'
              >
                <div className='h-12 w-12 rounded-full bg-slate-100 flex items-center justify-center mb-4 group-hover:bg-blue-50 transition-colors'>
                  <span className='text-2xl'>C</span>
                </div>
                <h3 className='font-semibold text-lg'>Context-Aware</h3>
                <p className='text-sm text-(--text-secondary) mt-2'>
                  Upload notes for improved accuracy.
                </p>
              </button>
            </div>

            {isCreating && (
              <p className='text-sm text-(--brand) mt-4 animate-pulse'>
                Initializing session...
              </p>
            )}
          </div>
        )}

        {sessionState === 'NOTES_REQUIRED' && sessionId && (
          <NotesUpload
            sessionId={sessionId}
            onSuccess={() => {
              setStatusMsg('Notes uploaded. Session is ready.');
              setSessionState('READY');
            }}
            onCancel={() => {
              void finalizeAsEnded();
            }}
          />
        )}

        {sessionState === 'READY' && (
          <div className='space-y-6 text-center'>
            <h2 className='text-2xl font-bold text-foreground'>
              Ready to Start
            </h2>
            <p className='text-(--text-secondary)'>
              Session is initialized. You can now begin live caption streaming.
            </p>
            <button
              onClick={() => {
                void handleStartRecording();
              }}
              disabled={isStarting || finalizePendingRef.current}
              className='px-8 py-3 bg-(--brand) text-(--brand-text) font-bold rounded-full shadow hover:bg-(--brand-accent) transition-colors mt-8 mx-auto block disabled:opacity-60 disabled:cursor-not-allowed'
            >
              {isStarting ? 'Starting...' : 'Start Recording'}
            </button>

            <div className='mt-8 flex justify-center gap-4'>
              <button
                onClick={() => {
                  void finalizeAsEnded();
                }}
                className='text-sm font-medium text-(--text-secondary) hover:text-foreground border border-(--input-border) px-6 py-2 rounded-full hover:bg-(--card-bg) transition-colors'
              >
                Cancel Session
              </button>
              {mode === 'context' && (
                <span className='text-xs text-(--text-secondary) self-center'>
                  Context mode enabled
                </span>
              )}
            </div>
          </div>
        )}

        {sessionState === 'STREAMING' && (
          <div className='space-y-6'>
            <div className='text-center'>
              <h2 className='text-2xl font-bold text-foreground'>
                Live Transcription
              </h2>
              <p className='text-(--text-secondary) mt-2'>
                Capturing audio and streaming live captions.
              </p>
            </div>

            <div className='grid grid-cols-1 sm:grid-cols-3 gap-3 text-sm'>
              <div className='rounded-xl border border-(--input-border) bg-(--input-bg) p-3 text-center'>
                <p className='text-(--text-secondary)'>Chunks Sent</p>
                <p className='font-semibold text-lg'>{chunkCount}</p>
              </div>
              <div className='rounded-xl border border-(--input-border) bg-(--input-bg) p-3 text-center'>
                <p className='text-(--text-secondary)'>Mic Permission</p>
                <p className='font-semibold text-lg capitalize'>
                  {permissionStatus}
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
                <div className='max-h-48 overflow-y-auto rounded-xl border border-(--input-border) bg-white/60 dark:bg-slate-900/30 p-3 space-y-2'>
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
                disabled={!isRecording || finalizePendingRef.current}
                className='px-8 py-3 bg-red-600 text-white font-bold rounded-full shadow hover:bg-red-700 transition-colors disabled:opacity-60 disabled:cursor-not-allowed'
              >
                Stop Recording
              </button>
            </div>
          </div>
        )}

        {sessionState === 'FINALIZING' && (
          <div className='space-y-6 text-center'>
            <h2 className='text-2xl font-bold text-foreground'>
              Finalizing Session
            </h2>
            <p className='text-(--text-secondary)'>
              {statusMsg ?? 'Saving session state...'}
            </p>
            <div className='mx-auto h-8 w-8 animate-spin rounded-full border-4 border-(--brand) border-t-transparent'></div>
          </div>
        )}

        {sessionState === 'COMPLETE' && (
          <div className='space-y-6 text-center'>
            <h2 className='text-2xl font-bold text-foreground'>
              Session Complete
            </h2>
            <p className='text-(--text-secondary)'>
              The session has ended cleanly. You can download the final PDF
              report.
            </p>
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
                onClick={resetToInit}
                className='px-6 py-2 border border-(--input-border) rounded-full hover:bg-(--card-bg) transition-colors'
              >
                Start New Session
              </button>
            </div>
          </div>
        )}

        {sessionState === 'ERROR' && (
          <div className='space-y-6 text-center text-red-600'>
            <h2 className='text-2xl font-bold'>Error</h2>
            <p className='text-sm bg-red-50 p-4 rounded-xl border border-red-200'>
              {errorMsg || 'An unknown error occurred.'}
            </p>
            <button
              onClick={resetToInit}
              className='px-8 py-3 bg-red-600 text-white font-bold rounded-full shadow hover:bg-red-700 transition-colors mt-8 mx-auto block'
            >
              Start New Session
            </button>
          </div>
        )}

        {statusMsg && sessionState !== 'FINALIZING' && (
          <p className='text-xs text-(--text-secondary) text-center mt-2'>
            {statusMsg}
          </p>
        )}
      </div>
    </div>
  );
}
