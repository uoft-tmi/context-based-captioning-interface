'use client';
import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { AccountOverview, deleteSession, downloadSessionPdf, getAccount, listSessions, SessionSummary } from '@/lib/api';
import { hasTranscript, recordingTime, saveDownload, sessionDate, sessionStatus } from '@/lib/session-utils';
import { Icon, Loading, Notice } from '@/components/ui';
import { deleteSessionBatch } from '@/lib/session-deletion';

export default function Dashboard() {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [account, setAccount] = useState<AccountOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [message, setMessage] = useState('');
  const load = useCallback(async () => {
    try { const [rows, plan] = await Promise.all([listSessions(), getAccount()]); setSessions(rows); setAccount(plan); setError(''); return ''; }
    catch (e) { const reason = e instanceof Error ? e.message : 'Unable to load your sessions.'; setError(reason); return reason; }
    finally { setLoading(false); }
  }, []);
  useEffect(() => {
    void Promise.all([listSessions(), getAccount()]).then(([rows, plan]) => { setSessions(rows); setAccount(plan); }).catch((e) => setError(e.message)).finally(() => setLoading(false));
  }, []);
  const active = sessions.find((session) => session.is_active && !session.deleting_at);
  const visible = sessions.filter((session) => session.name.toLowerCase().includes(search.toLowerCase()));
  const deletable = sessions.filter((session) => !session.is_recording);
  const selected = deletable.filter((session) => selectedIds.includes(session.id));
  const selectableVisible = visible.filter((session) => !session.is_recording);
  const allShownSelected = selectableVisible.length > 0 && selectableVisible.every((session) => selectedIds.includes(session.id));
  const recordingCount = sessions.length - deletable.length;

  function toggleShown() {
    const ids = new Set(selectableVisible.map((session) => session.id));
    setSelectedIds((current) => allShownSelected ? current.filter((id) => !ids.has(id)) : [...new Set([...current, ...ids])]);
  }
  async function remove(targets: SessionSummary[], all = false) {
    const description = all ? `all ${targets.length} sessions across your dashboard (including sessions hidden by search)` : targets.length === 1 ? `“${targets[0].name}”` : `${targets.length} selected sessions`;
    const recordingNote = all && recordingCount ? ` ${recordingCount} recording session(s) will be kept.` : '';
    if (busy || targets.length === 0 || !window.confirm(`Delete ${description} and all their files and transcripts? This cannot be undone.${recordingNote}`)) return;
    setBusy('deleting'); setError(''); setMessage('');
    try {
      const result = await deleteSessionBatch(targets, deleteSession);
      setSelectedIds((current) => [...new Set([...current.filter((id) => !result.deleted.includes(id)), ...result.failed.map((failure) => failure.id)])]);
      const refreshError = await load();
      setError([result.failed.length ? `${result.failed.length} session(s) could not be deleted. ${result.failed.map((failure) => `${failure.name}: ${failure.message}`).join(' ')}` : '', refreshError].filter(Boolean).join(' '));
      setMessage(`${result.deleted.length} session(s) deleted.${result.skipped.length ? ` ${result.skipped.length} recording session(s) kept.` : ''}`);
    }
    finally { setBusy(null); }
  }
  async function download(session: SessionSummary) {
    setBusy(session.id);
    try { saveDownload(await downloadSessionPdf(session.id), `${session.name}.pdf`); }
    catch (e) { setError(e instanceof Error ? e.message : 'Download failed.'); }
    finally { setBusy(null); }
  }
  return <section>
    <div className="dashboard-heading"><div><p className="eyebrow">Your lecture workspace</p><h1>Pick up where you left off.</h1><p className="muted">Every session, transcript, and lecture file in one place.</p></div>
      {active ? <Link className="btn btn-primary" href={`/session/${active.id}`}>Open active session <Icon name="arrow" /></Link> : <Link className="btn btn-primary" href="/session/new">Create session <Icon name="arrow" /></Link>}
    </div>
    {error && <Notice tone="error">{error} <button className="text-link" disabled={busy !== null} onClick={() => void load()}>Refresh sessions</button></Notice>}
    {message && <div role="status"><Notice>{message}</Notice></div>}
    {account && <div className="workspace-summary"><span className="tag">{account.plan === 'paid' ? 'Paid plan' : 'Free plan'}</span><span>{recordingTime(account.recording_limit_seconds * 1000)} recording per session</span><span>{sessions.length} sessions</span><span>{sessions.filter(hasTranscript).length} saved transcripts</span></div>}
    {active && <Notice>One session at a time. Open <Link href={`/session/${active.id}`}>{active.name}</Link> to record, or end it before creating another.</Notice>}
    <div className="section-heading dashboard-section"><h2>All sessions</h2><label className="search-field"><span className="sr-only">Search sessions</span><input className="text-input" placeholder="Search session names…" value={search} onChange={(e) => setSearch(e.target.value)} /></label></div>
    {!loading && sessions.length > 0 && <div className="session-selection-toolbar">
      <div className="session-selection-actions"><button className="btn btn-secondary btn-small" disabled={busy !== null || selectableVisible.length === 0} onClick={toggleShown}>{allShownSelected ? 'Deselect all shown' : 'Select all shown'}</button><span className="muted small" role="status">{selected.length} selected</span>{selected.length > 0 && <button className="text-link" disabled={busy !== null} onClick={() => setSelectedIds([])}>Clear selection</button>}</div>
      <div className="session-selection-actions"><button className="btn btn-danger btn-small" disabled={busy !== null || selected.length === 0} onClick={() => void remove(selected)}>Delete selected ({selected.length})</button><button className="btn btn-secondary btn-small delete-link" disabled={busy !== null || deletable.length === 0} onClick={() => void remove(deletable, true)}>Delete all ({deletable.length})</button></div>
      {recordingCount > 0 && <p className="muted small selection-note">Sessions currently recording cannot be selected or deleted.</p>}
      {busy === 'deleting' && <p className="muted small selection-note" role="status">Deleting sessions…</p>}
    </div>}
    {loading ? <Loading /> : sessions.length === 0 ? <div className="panel empty-library"><Icon name="captions" width="36" height="36" /><h2>Your first lecture starts here.</h2><p className="muted">Name a session, add your materials, and start captioning. Sessions stay here until you delete them.</p><Link className="btn btn-primary" href="/session/new">Create your first session <Icon name="arrow" /></Link></div> : <div className="session-grid">
      {visible.length === 0 && <p className="muted">No sessions match your search.</p>}
      {visible.map((session) => <article className={`panel session-card${selected.some((item) => item.id === session.id) ? ' session-card-selected' : ''}`} key={session.id}>
        <label className="session-select"><input type="checkbox" checked={selected.some((item) => item.id === session.id)} disabled={busy !== null || session.is_recording} onChange={(event) => { const checked = event.target.checked; setSelectedIds((current) => checked ? [...current, session.id] : current.filter((id) => id !== session.id)); }} /><span>Select session <span className="sr-only">{session.name}</span></span></label>
        <div className="section-heading"><span className={`tag ${session.is_active ? '' : 'tag-neutral'}`}>{sessionStatus(session)}</span><span className="muted small">{recordingTime(session.recorded_duration_ms)}</span></div>
        <h3><Link href={`/session/${session.id}`}>{session.name}</Link></h3><p className="muted small">{sessionDate(session.created_at)}</p><p className="muted small">{session.mode === 'context' ? 'With lecture notes' : 'Audio-only captions'}</p>
        <div className="session-actions"><Link className="btn btn-secondary btn-small" href={`/session/${session.id}`}>Session details</Link>{hasTranscript(session) && <><Link className="text-link" href={`/session/${session.id}/transcript`}>Read transcript</Link><button className="icon-button" aria-label={`Download transcript for ${session.name}`} disabled={busy !== null} onClick={() => void download(session)}><Icon name="download" /></button></>}</div>
        <button className="text-link delete-link" disabled={busy !== null || session.is_recording} onClick={() => void remove([session])}>{session.deleting_at ? 'Retry deletion' : 'Delete session'}</button>
      </article>)}
    </div>}
  </section>;
}
