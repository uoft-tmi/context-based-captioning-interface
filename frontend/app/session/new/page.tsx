'use client';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { createSession, getAccount, getProviderCapabilities, listSessions, AccountOverview, ProviderCapabilities, SessionMode, SessionSummary } from '@/lib/api';
import { normalizeSessionName, recordingTime } from '@/lib/session-utils';
import { Icon, Loading, Notice, Steps } from '@/components/ui';

export default function CreateSessionPage() {
  const router = useRouter();
  const [name, setName] = useState('');
  const [mode, setMode] = useState<SessionMode>('baseline');
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [provider, setProvider] = useState<ProviderCapabilities | null>(null);
  const [account, setAccount] = useState<AccountOverview | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    void Promise.all([listSessions(), getProviderCapabilities(), getAccount()]).then(([rows, caps, plan]) => { setSessions(rows); setProvider(caps); setAccount(plan); }).catch((e) => setError(e.message)).finally(() => setLoading(false));
  }, []);
  const active = sessions.find((s) => s.is_active && !s.deleting_at);
  const duplicate = sessions.some((s) => normalizeSessionName(s.name).toLowerCase() === normalizeSessionName(name).toLowerCase());
  async function create(event: React.FormEvent) {
    event.preventDefault();
    if (saving || active || duplicate || !name.trim()) return;
    setSaving(true); setError('');
    try { const session = await createSession(mode, normalizeSessionName(name)); router.push(`/session/${session.id}`); }
    catch (e) { setError(e instanceof Error ? e.message : 'Unable to create session.'); setSaving(false); }
  }
  return <section><Steps current={0} /><div className="page-heading"><p className="eyebrow">A new lecture</p><h1>Give your session a name.</h1><p className="muted">A clear name makes your transcript and files easy to find later.</p></div>
    {error && <Notice tone="error">{error}</Notice>}
    {loading ? <Loading /> : active ? <Notice>You already have an active session: <Link href={`/session/${active.id}`}>{active.name}</Link>. End it before creating another.</Notice> : <form className="panel create-session-form" onSubmit={(e) => void create(e)}>
      <div className="panel-body"><label className="field-label" htmlFor="session-name">Session name</label><input className="text-input" id="session-name" placeholder="e.g. CSC343 - Introduction to Databases" value={name} maxLength={120} required disabled={saving} onChange={(e) => setName(e.target.value)} aria-describedby="session-name-help" /><p id="session-name-help" className={duplicate ? 'name-error' : 'muted small'}>{duplicate ? 'You already have a session with this name. Choose a different name or delete the old session.' : 'Up to 120 characters. Names must be unique across your sessions.'}</p>
        <fieldset className="choice-list" disabled={saving}><legend className="field-label">Captioning mode</legend><label className={`choice ${mode === 'baseline' ? 'selected' : ''}`}><input type="radio" checked={mode === 'baseline'} onChange={() => setMode('baseline')} name="mode" /><span className="choice-copy"><span className="choice-title">Audio only</span><span className="choice-description">Start with your microphone. You can still keep uploaded files with this session.</span></span><Icon name="mic" /></label>
        <label className={`choice ${mode === 'context' ? 'selected' : ''} ${!provider?.supports_pdf_notes ? 'unavailable' : ''}`}><input type="radio" checked={mode === 'context'} onChange={() => setMode('context')} disabled={!provider?.supports_pdf_notes} name="mode" /><span className="choice-copy"><span className="choice-title">Use lecture notes</span><span className="choice-description">Help the captioning model recognize course terminology.{!provider?.supports_pdf_notes && ' Your current service does not support note context.'}</span></span><Icon name="file" /></label></fieldset>
        {account && <p className="plan-caption">{account.plan === 'paid' ? 'Paid plan' : 'Free plan'} · Up to {recordingTime(account.recording_limit_seconds * 1000)} of recording. Preparation time does not count.</p>}
      </div><div className="panel-footer"><Link className="btn btn-ghost" href="/session">Back to dashboard</Link><button className="btn btn-primary" disabled={saving || duplicate || !name.trim() || !provider}>{saving ? 'Creating…' : 'Create session'} <Icon name="arrow" /></button></div>
    </form>}
  </section>;
}
