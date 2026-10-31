'use client';
import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { downloadSessionPdf, getSessionDetails, SessionSummary } from '@/lib/api';
import { hasTranscript, recordingTime, saveDownload, sessionDate } from '@/lib/session-utils';
import { Icon, Loading, Notice, Steps } from '@/components/ui';

export default function TranscriptPage() {
  const { id } = useParams<{ id: string }>();
  const [session, setSession] = useState<SessionSummary | null>(null);
  const [error, setError] = useState('');
  const [downloading, setDownloading] = useState(false);
  useEffect(() => { void getSessionDetails(id).then(setSession).catch((e) => setError(e.message)); }, [id]);
  async function download() {
    if (!session) return;
    setDownloading(true);
    try { saveDownload(await downloadSessionPdf(id), `${session.name}.pdf`); }
    catch (e) { setError(e instanceof Error ? e.message : 'Unable to download transcript.'); }
    finally { setDownloading(false); }
  }
  if (!session) return <>{error ? <Notice tone="error">{error}</Notice> : <Loading />}<Link className="text-link" href="/session">Back to dashboard</Link></>;
  return <section><Steps current={3} /><div className="dashboard-heading"><div><p className="eyebrow">Your saved transcript</p><h1>{session.name}</h1><p className="muted">{sessionDate(session.created_at)} · {recordingTime(session.recorded_duration_ms)} recorded</p></div>{hasTranscript(session) && <button className="btn btn-primary" disabled={downloading} onClick={() => void download()}><Icon name="download" />{downloading ? 'Downloading…' : 'Download PDF'}</button>}</div>
    {error && <Notice tone="error">{error}</Notice>}
    <article className="panel transcript-document"><p className="eyebrow">Lecture transcript</p>{session.transcript_text !== null ? session.transcript_text.trim() ? session.transcript_text.split(/\n\s*\n/).map((paragraph, index) => <p className="transcript-paragraph" key={index}>{paragraph}</p>) : <p className="muted">No speech was captured during this session.</p> : <p className="muted">{session.transcript_key ? 'The saved PDF is available above. This older transcript does not have a text preview.' : 'No transcript was saved for this session.'}</p>}</article>
    <div className="transcript-navigation"><Link className="btn btn-secondary" href={`/session/${id}`}>Session details</Link><Link className="btn btn-primary" href="/session">Back to dashboard <Icon name="arrow" /></Link></div><p className="muted small">Your session, transcript, and uploaded files remain available until you delete them.</p>
  </section>;
}
