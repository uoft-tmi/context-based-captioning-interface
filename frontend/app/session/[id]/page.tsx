'use client';
import { useCallback, useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { deleteSessionNote, downloadSessionNote, endSession, getProviderCapabilities, getSessionDetails, listSessionNotes, ProviderCapabilities, SessionSummary } from '@/lib/api';
import { hasTranscript, recordingTime, saveDownload, sessionDate, sessionStatus } from '@/lib/session-utils';
import NotesUpload from '@/components/notes-upload';
import { Icon, Loading, Notice, Steps } from '@/components/ui';

export default function SessionDetails() {
  const { id } = useParams<{ id: string }>();
  const [session, setSession] = useState<SessionSummary | null>(null);
  const [files, setFiles] = useState<string[]>([]);
  const [provider, setProvider] = useState<ProviderCapabilities | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    try { const [details, notes, caps] = await Promise.all([getSessionDetails(id), listSessionNotes(id), getProviderCapabilities()]); setSession(details); setFiles(notes); setProvider(caps); setError(''); }
    catch (e) { setError(e instanceof Error ? e.message : 'Unable to load this session.'); }
  }, [id]);
  useEffect(() => {
    void Promise.all([getSessionDetails(id), listSessionNotes(id), getProviderCapabilities()]).then(([details, notes, caps]) => { setSession(details); setFiles(notes); setProvider(caps); }).catch((e) => setError(e.message));
  }, [id]);
  async function download(filename: string) {
    setBusy(true);
    try { saveDownload(await downloadSessionNote(id, filename), filename); }
    catch (e) { setError(e instanceof Error ? e.message : 'Unable to download file.'); }
    finally { setBusy(false); }
  }
  async function remove(filename: string) {
    if (!window.confirm(`Delete “${filename}” from this session?`)) return;
    setBusy(true);
    try { await deleteSessionNote(id, filename); await load(); }
    catch (e) { setError(e instanceof Error ? e.message : 'Unable to delete file.'); }
    finally { setBusy(false); }
  }
  async function end() {
    setBusy(true);
    try { await endSession(id); await load(); }
    catch (e) { setError(e instanceof Error ? e.message : 'Unable to end session.'); }
    finally { setBusy(false); }
  }
  if (!session) return <>{error ? <Notice tone="error">{error}</Notice> : <Loading />}<Link href="/session" className="text-link">Back to dashboard</Link></>;
  const canRecord = session.is_active && !session.is_recording && !session.deleting_at;
  const incompatible = (session.mode === 'context' && !provider?.supports_pdf_notes) || provider?.transcription_enabled === false;
  return <section><Steps current={1} /><div className="dashboard-heading"><div><p className="eyebrow">Session details</p><h1>{session.name}</h1><p className="muted">{sessionDate(session.created_at)}</p></div><span className="tag">{sessionStatus(session)}</span></div>
    {error && <Notice tone="error">{error}</Notice>}
    {session.error && <Notice tone="warning">This session ended with an issue. Any saved transcript and uploaded files remain available.</Notice>}
    <div className="setup-grid"><div className="panel"><div className="panel-body"><h2>Your lecture files</h2><p className="muted small">Files stay with this session until you delete them. You can also find them in your file library.</p>
      {files.length > 0 ? <ul className="file-list">{files.map((filename) => <li key={filename}><Icon name="file" /><span>{filename}</span><button className="icon-button" disabled={busy} aria-label={`Download ${filename}`} onClick={() => void download(filename)}><Icon name="download" /></button><button className="text-link delete-link" disabled={busy || session.is_recording} onClick={() => void remove(filename)}>Delete</button></li>)}</ul> : <p className="empty-files muted">No files uploaded yet.</p>}
      {canRecord && files.length < 3 && <NotesUpload compact sessionId={id} disabled={busy} onSuccess={() => void load()} onSkip={() => {}} onCancel={() => {}} />}
      {!provider?.supports_pdf_notes && <p className="muted small">Your current captioning service stores these files for reference but does not use them to generate captions.</p>}
    </div><div className="panel-footer"><Link className="btn btn-ghost" href="/session">Dashboard</Link>{canRecord ? <Link className={`btn btn-primary ${incompatible ? 'disabled-link' : ''}`} aria-disabled={incompatible} href={incompatible ? '#' : `/session/live?sessionId=${id}`}>Continue to recording <Icon name="mic" /></Link> : hasTranscript(session) ? <Link className="btn btn-primary" href={`/session/${id}/transcript`}>Read transcript <Icon name="arrow" /></Link> : <span className="muted small">{session.is_recording ? 'Recording is open in another tab.' : 'This session has ended.'}</span>}</div></div>
      <aside className="panel help-card"><p className="eyebrow">Recording allowance</p><h2>{recordingTime(session.recording_limit_seconds * 1000)} per session</h2><p className="muted small" style={{ marginTop: 12 }}>Recording stops automatically at your limit and saves your transcript. Preparation and file upload time do not count.</p><p className="plan-caption">Recorded: {recordingTime(session.recorded_duration_ms)}</p>{session.is_active && <button className="btn btn-secondary" disabled={busy || session.is_recording} onClick={() => void end()}>{busy ? 'Working…' : 'End session without recording'}</button>}</aside>
    </div>
  </section>;
}
