'use client';

import { Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { downloadSessionPdf, endSession, getProviderCapabilities, getSessionDetails, getSessionStreamUrlWithAuth, type ProviderCapabilities, type SessionSummary } from '@/lib/api';
import { useAudioChunker, type AudioChunk } from '@/lib/audio/useAudioChunker';
import { CaptionStream } from '@/lib/stream-client';
import { Icon, Loading, Notice, Steps } from '@/components/ui';

type State = 'LOADING' | 'READY' | 'CONNECTING' | 'STREAMING' | 'FINALIZING' | 'COMPLETE' | 'ERROR';

function LiveSessionContent() {
  const router = useRouter();
  const sessionId = useSearchParams().get('sessionId');
  const [capabilities, setCapabilities] = useState<ProviderCapabilities | null>(null);
  const [session, setSession] = useState<SessionSummary | null>(null);
  const [state, setState] = useState<State>('LOADING');
  const [error, setError] = useState('');
  const [warning, setWarning] = useState('');
  const [captions, setCaptions] = useState<string[]>([]);
  const [finalTranscript, setFinalTranscript] = useState<string | null>(null);
  const [latencies, setLatencies] = useState<number[]>([]);
  const [downloading, setDownloading] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [textSize, setTextSize] = useState(22);
  const [fullscreen, setFullscreen] = useState(false);
  const [following, setFollowing] = useState(true);
  const [elapsed, setElapsed] = useState(0);
  const [canRetryMic, setCanRetryMic] = useState(false);
  const stream = useRef<CaptionStream | null>(null);
  const panel = useRef<HTMLDivElement>(null);
  const captionBody = useRef<HTMLDivElement>(null);
  const recordingStarted = useRef(0);
  const mounted = useRef(true);
  const starting = useRef(false);
  const finishing = useRef(false);
  const cancellingRef = useRef(false);

  const sendChunk = useCallback(async (chunk: AudioChunk) => {
    if (!stream.current) throw new Error('Captioning stream is not connected.');
    await stream.current.sendChunk({ chunk_index: chunk.chunkIndex, audio: chunk.audio, capturedAtMs: chunk.capturedAtMs });
  }, []);
  const audio = useAudioChunker({ chunkDurationMs: capabilities?.recommended_chunk_ms ?? 2500, initialChunkDurationMs: capabilities?.initial_chunk_ms ?? undefined, minRequestIntervalMs: capabilities?.min_request_interval_ms ?? 0, onChunk: sendChunk, onError: (message) => {
    if (!mounted.current) return;
    setError(message);
    setState('ERROR');
    setCanRetryMic(false);
    stream.current?.close();
    audio.stop();
  } });
  const { stop, flushAndStop } = audio;
  const active = state === 'STREAMING' || state === 'FINALIZING' || state === 'CONNECTING';

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; stream.current?.close(); stop(); };
  }, [stop]);

  useEffect(() => {
    let cancelled = false;
    if (!sessionId) return;
    void Promise.all([getSessionDetails(sessionId), getProviderCapabilities()]).then(([details, provider]) => {
      if (cancelled) return;
      setSession(details);
      setCapabilities(provider);
      if (details.mode === 'context' && !provider.supports_pdf_notes && details.is_active) {
        setError('This provider cannot use lecture notes. Return to setup, cancel this session, and choose Audio only.');
        setState('ERROR');
      } else if (details.transcript_key && !details.is_active) setState('COMPLETE');
      else if (!details.is_active || new Date(details.expires_at).getTime() <= Date.now()) {
        setError('This session has ended. Return to setup to start a new lecture.');
        setState('ERROR');
      } else setState('READY');
    }).catch((error: unknown) => {
      if (!cancelled) { setError(error instanceof Error ? error.message : 'Unable to load the session.'); setState('ERROR'); }
    });
    return () => { cancelled = true; };
  }, [sessionId]);

  useEffect(() => {
    if (!active) return;
    const beforeUnload = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', beforeUnload);
    return () => window.removeEventListener('beforeunload', beforeUnload);
  }, [active]);

  useEffect(() => {
    if (state !== 'STREAMING') return;
    const timer = setInterval(() => setElapsed(Math.floor((Date.now() - recordingStarted.current) / 1000)), 1000);
    return () => clearInterval(timer);
  }, [state]);

  useEffect(() => {
    if (following && captionBody.current) captionBody.current.scrollTop = captionBody.current.scrollHeight;
  }, [captions, finalTranscript, following, textSize]);

  useEffect(() => {
    const onFullscreen = () => setFullscreen(document.fullscreenElement === panel.current);
    document.addEventListener('fullscreenchange', onFullscreen);
    return () => document.removeEventListener('fullscreenchange', onFullscreen);
  }, []);

  async function startRecording() {
    if (!sessionId || starting.current) return;
    starting.current = true;
    setState('CONNECTING');
    setError('');
    setWarning('');
    setCanRetryMic(false);
    let microphoneReady = false;
    try {
      // Ask for permission before the backend's inactivity timer starts.
      if (!await audio.prepare() || !mounted.current) return;
      microphoneReady = true;
      const url = await getSessionStreamUrlWithAuth(sessionId);
      if (!mounted.current) return;
      const client = new CaptionStream({
        onReady: (limit) => setSession((previous) => previous ? { ...previous, recording_limit_seconds: limit } : previous),
        onCaption: (text, _index, latencyMs) => {
          if (!mounted.current) return;
          setCaptions((previous) => [...previous, text]);
          setLatencies((previous) => [...previous, latencyMs]);
        },
        onFinal: (text) => {
          stop();
          if (!mounted.current) return;
          setFinalTranscript(text);
          setState('COMPLETE');
          router.replace(`/session/${sessionId}/transcript`);
        },
        onWarning: (text) => { if (mounted.current) setWarning(text); },
        onError: (error) => {
          stop();
          if (mounted.current) { setError(error.message); setState('ERROR'); setCanRetryMic(false); }
        },
      });
      stream.current = client;
      await client.connect(url);
      if (!mounted.current) { client.close(); return; }
      await audio.start();
      if (mounted.current && client.isActive) {
        recordingStarted.current = Date.now();
        setElapsed(0);
        setState('STREAMING');
      }
    } catch (error) {
      stream.current?.close();
      stop();
      if (mounted.current) {
        const permissionDenied = error instanceof Error && ['NotAllowedError', 'PermissionDeniedError'].includes(error.name);
        setError(permissionDenied ? 'Microphone access is blocked. Allow microphone access in your browser’s site settings, then try again.' : error instanceof Error ? error.message : 'Unable to start recording. Check your microphone and try again.');
        setCanRetryMic(!microphoneReady);
        setState('ERROR');
      }
    } finally { starting.current = false; }
  }

  const finish = useCallback(async () => {
    if (finishing.current) return;
    finishing.current = true;
    setState('FINALIZING');
    try {
      await flushAndStop();
      await stream.current?.finish();
    } catch (error) {
      stream.current?.close();
      stop();
      if (mounted.current) { setError(error instanceof Error ? error.message : 'Unable to save the transcript.'); setCanRetryMic(false); setState('ERROR'); }
    } finally { finishing.current = false; }
  }, [flushAndStop, stop]);

  useEffect(() => {
    if (state !== 'STREAMING' || !session) return;
    const remaining = session.recording_limit_seconds * 1000 - (Date.now() - recordingStarted.current);
    const timer = setTimeout(() => void finish(), Math.max(0, remaining));
    return () => clearTimeout(timer);
  }, [state, session, finish]);

  function saveBlob(blob: Blob, filename: string) {
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  async function download() {
    if (!sessionId || downloading) return;
    setDownloading(true);
    setError('');
    try { saveBlob(await downloadSessionPdf(sessionId), `lecture-transcript-${session?.created_at.slice(0, 10) ?? sessionId}.pdf`); }
    catch (error) { setError(error instanceof Error ? error.message : 'Unable to download the transcript. Please try again.'); }
    finally { setDownloading(false); }
  }

  async function cancel() {
    if (!sessionId || cancellingRef.current) return;
    cancellingRef.current = true;
    setCancelling(true);
    setError('');
    try { await endSession(sessionId); router.push('/session'); }
    catch (error) { setError(error instanceof Error ? error.message : 'Unable to cancel the session.'); }
    finally { setCancelling(false); cancellingRef.current = false; }
  }

  async function toggleFullscreen() {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else if (panel.current?.requestFullscreen) await panel.current.requestFullscreen();
      else setWarning('Full screen is unavailable in this browser. You can still increase the caption text size.');
    } catch { setWarning('Full screen could not open. You can still increase the caption text size.'); }
  }

  const transcript = finalTranscript ?? captions.join('\n');
  const sorted = [...latencies].sort((a, b) => a - b);
  const p95 = sorted[Math.max(0, Math.ceil(sorted.length * 0.95) - 1)];
  const complete = state === 'COMPLETE';
  const status = { LOADING: 'Loading', READY: 'Ready to begin', CONNECTING: 'Connecting', STREAMING: 'Recording', FINALIZING: 'Saving transcript', COMPLETE: 'Transcript saved', ERROR: 'Recording unavailable' }[state];
  const time = `${Math.floor(elapsed / 60).toString().padStart(2, '0')}:${(elapsed % 60).toString().padStart(2, '0')}`;

  if (!sessionId) return <><Steps current={0} /><Notice tone="error">No lecture was selected. Return to setup to begin.</Notice><button className="btn btn-primary" onClick={() => router.push('/session')}>Back to setup <Icon name="arrow" /></button></>;
  if (state === 'LOADING') return <><Steps current={1} /><Loading>Opening your lecture…</Loading></>;

  return <section>
    <Steps current={complete ? 3 : 2} />
    <div className="caption-heading page-heading"><div><p className="eyebrow">{complete ? 'Lecture complete' : 'Your lecture, in words'}</p><h1>{session?.name ?? (complete ? 'Your transcript is ready.' : 'Live lecture captions')}</h1><p className="muted small">{complete ? 'Saved and ready to take with you.' : 'Start your microphone, then focus on teaching.'}</p></div>
      <span role="status" className={`status-pill ${state === 'STREAMING' ? 'status-recording' : state === 'ERROR' ? 'status-neutral' : ''}`}><span className="status-dot" />{status}{state === 'STREAMING' && <span aria-label="Recording duration"> · {time}</span>}</span>
    </div>
    {session && !complete && <p className="plan-caption">Recording allowance: {Math.floor(session.recording_limit_seconds / 60).toString().padStart(2, '0')}:{(session.recording_limit_seconds % 60).toString().padStart(2, '0')} · Recording stops and saves automatically.</p>}
    {capabilities?.name === 'mock'  && <Notice tone="warning"><strong>Demo mode.</strong> These are sample captions, not a transcription of your speech.</Notice>}
    {error && <Notice tone="error">{error}</Notice>}
    {warning && <Notice tone="warning">{warning}</Notice>}
    {state === 'ERROR' && <Notice>{transcript ? 'The transcript has not been confirmed as saved. You can download the visible captions below to keep a copy.' : 'Your microphone is off. Return to setup to continue.'}</Notice>}
    <div ref={panel} className="panel caption-panel">
      <div className="caption-toolbar"><h2 id="caption-title">{complete ? 'Lecture transcript' : 'Captions'}</h2><div className="toolbar-controls">
        <label className="size-label"><span>Text size</span><select aria-label="Caption text size" value={textSize} onChange={(event) => setTextSize(Number(event.target.value))}><option value={22}>Standard</option><option value={28}>Large</option><option value={36}>Extra large</option></select></label>
        <button className="icon-button" title={fullscreen ? 'Exit full screen' : 'Full screen captions'} aria-label={fullscreen ? 'Exit full screen' : 'Full screen captions'} onClick={() => void toggleFullscreen()}><Icon name={fullscreen ? 'close' : 'expand'} width="17" height="17" /></button>
      </div></div>
      <div ref={captionBody} className="caption-body" role="region" aria-labelledby="caption-title" tabIndex={0} onScroll={(event) => { const element = event.currentTarget; setFollowing(element.scrollHeight - element.scrollTop - element.clientHeight < 64); }}>
        {transcript ? <div className="caption-text" style={{ fontSize: textSize }}>{finalTranscript !== null ? <p>{finalTranscript}</p> : <div role="log" aria-label="Live captions" aria-live="polite" aria-relevant="additions">{captions.map((text, index) => <p key={index} className="caption-paragraph">{text}</p>)}</div>}</div> : <div className="caption-empty"><span className="empty-icon"><Icon name={complete ? 'file' : 'captions'} width="28" height="28" /></span><h2>{complete ? finalTranscript === '' ? 'No speech was captured' : 'Your transcript is saved' : state === 'STREAMING' ? 'Listening to your lecture…' : state === 'CONNECTING' ? 'Getting everything ready…' : state === 'FINALIZING' ? 'Saving your transcript…' : state === 'ERROR' ? 'Captioning has stopped' : 'A clear space for your words.'}</h2><p>{complete ? finalTranscript === '' ? 'The saved PDF is available below.' : 'Download the PDF below to read your saved lecture transcript.' : state === 'STREAMING' ? 'Your captions will appear here as you speak. The first words may take a few seconds.' : state === 'CONNECTING' ? 'Allow microphone access if asked. The captioning service may take a moment to prepare.' : state === 'FINALIZING' ? 'Please keep this tab open while your transcript is saved.' : state === 'ERROR' ? 'Check the message above for your next step.' : 'Once you start recording, your lecture will appear here as easy-to-read captions.'}</p></div>}
      </div>
      {!following && transcript && <div style={{ textAlign: 'center', paddingBottom: 12 }}><button className="btn btn-secondary btn-small" onClick={() => setFollowing(true)}>Jump to latest captions</button></div>}
      <div className="recording-bar">
        <div className="recording-info"><span className="mic-status"><Icon name={complete ? 'check' : 'mic'} width="18" height="18" /></span><div><p className="recording-label">{complete ? 'Transcript saved' : state === 'STREAMING' ? 'Microphone is on' : state === 'CONNECTING' ? 'Preparing your microphone' : state === 'FINALIZING' ? 'Microphone is off · Saving' : 'Microphone is off'}</p>
          {state === 'STREAMING' ? <div role="meter" aria-label="Microphone level" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(audio.audioLevel * 100)} className="mic-meter"><div style={{ width: `${audio.audioLevel * 100}%` }} /></div> : <p className="recording-hint">{complete ? 'Download a copy for your records.' : state === 'CONNECTING' ? 'Waiting for the captioning service…' : state === 'FINALIZING' ? 'Keep this page open until saving finishes.' : 'You control when recording starts.'}</p>}
        </div></div>
        {state === 'READY' && <button className="btn btn-primary" disabled={cancelling} onClick={() => void startRecording()}><Icon name="mic" width="17" height="17" />Start recording</button>}
        {state === 'CONNECTING' && <button className="btn btn-secondary" disabled><span className="spinner" />Connecting…</button>}
        {state === 'STREAMING' && <button className="btn btn-danger" disabled={!audio.isRecording} onClick={() => void finish()}><Icon name="stop" width="16" height="16" />Stop and save transcript</button>}
        {state === 'FINALIZING' && <button className="btn btn-secondary" disabled><span className="spinner" />Saving transcript…</button>}
        {complete && <button className="btn btn-primary" disabled={downloading} onClick={() => void download()}>{downloading ? <span className="spinner" /> : <Icon name="download" width="17" height="17" />}{downloading ? 'Downloading…' : 'Download transcript PDF'}</button>}
        {state === 'ERROR' && canRetryMic && <button className="btn btn-primary" onClick={() => void startRecording()}><Icon name="mic" width="17" height="17" />Try microphone again</button>}
        {state === 'ERROR' && transcript && <button className="btn btn-secondary" onClick={() => saveBlob(new Blob([transcript], { type: 'text/plain;charset=utf-8' }), 'lecture-captions-unsaved.txt')}><Icon name="download" width="17" height="17" />Download visible captions</button>}
      </div>
    </div>
    <div className="caption-footnote"><span>{complete ? 'You can start a new lecture whenever you’re ready.' : active ? 'Keep this tab open. Stop recording to save your transcript.' : 'Your browser will ask for microphone access when you start.'}</span>
      {state === 'READY' && <button className="text-link" disabled={cancelling} onClick={() => void cancel()}>{cancelling ? 'Cancelling…' : 'Cancel session'}</button>}
      {(complete || state === 'ERROR') && <button className="text-link" onClick={() => router.push('/session')}>{complete ? 'Start another lecture' : 'Back to setup'}</button>}
    </div>
    {latencies.length > 0 && <details className="diagnostics"><summary>Captioning details</summary><div className="diagnostic-values"><span>Audio segments: <strong>{audio.chunkCount}</strong></span><span>Captions: <strong>{captions.length}</strong></span><span>p95 caption delay: <strong>{p95 === undefined ? '—' : `${Math.round(p95)} ms`}</strong></span></div><p>Caption delay is estimated from the first audio sample in a segment to its caption response, including audio collection and queuing. The first segment is {(capabilities?.initial_chunk_ms ?? capabilities?.recommended_chunk_ms ?? 2500) / 1000} seconds; later segments are {(capabilities?.recommended_chunk_ms ?? 2500) / 1000} seconds.</p></details>}
  </section>;
}

export default function LiveSessionPage() {
  return <Suspense fallback={<Loading>Opening your lecture…</Loading>}><LiveSessionContent /></Suspense>;
}
