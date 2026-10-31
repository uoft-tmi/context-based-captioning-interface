'use client';
import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { downloadSessionNote, LibraryFile, listLibraryFiles } from '@/lib/api';
import { saveDownload, sessionDate } from '@/lib/session-utils';
import { Icon, Loading, Notice } from '@/components/ui';

export default function FileLibrary() {
  const [files, setFiles] = useState<LibraryFile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [busy, setBusy] = useState<string | null>(null);
  const load = useCallback(async () => {
    try { setFiles(await listLibraryFiles()); setError(''); }
    catch (e) { setError(e instanceof Error ? e.message : 'Unable to load your library.'); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void listLibraryFiles().then(setFiles).catch((e) => setError(e.message)).finally(() => setLoading(false)); }, []);
  const grouped = new Map<string, LibraryFile[]>();
  for (const file of files.filter((f) => `${f.session_name} ${f.filename}`.toLowerCase().includes(search.toLowerCase()))) {
    grouped.set(file.session_id, [...(grouped.get(file.session_id) ?? []), file]);
  }
  async function download(file: LibraryFile) {
    setBusy(file.id);
    try { saveDownload(await downloadSessionNote(file.session_id, file.filename), file.filename); }
    catch (e) { setError(e instanceof Error ? e.message : 'Unable to download file.'); }
    finally { setBusy(null); }
  }
  return <section><div className="dashboard-heading"><div><p className="eyebrow">Your file library</p><h1>Everything you brought to class.</h1><p className="muted">Uploaded PDFs, organized by session and kept after recording ends.</p></div><label className="search-field"><span className="sr-only">Search library</span><input className="text-input" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search files or sessions…" /></label></div>
    {error && <Notice tone="error">{error} <button className="text-link" onClick={() => void load()}>Try again</button></Notice>}
    {loading ? <Loading /> : files.length === 0 ? <div className="panel empty-library"><Icon name="file" width="36" height="36" /><h2>A home for your lecture files.</h2><p className="muted">Open a session and upload a PDF. It will stay here for future reference.</p><Link className="btn btn-primary" href="/session">Open dashboard <Icon name="arrow" /></Link></div> : grouped.size === 0 ? <p className="muted">No matching files.</p> : <div className="library-groups">{Array.from(grouped.entries()).map(([sessionId, group]) => <section className="panel library-group" key={sessionId}><div className="section-heading"><h2><Link href={`/session/${sessionId}`}>{group[0].session_name}</Link></h2><span className="tag tag-neutral">{group.length} {group.length === 1 ? 'file' : 'files'}</span></div><ul className="file-list">{group.map((file) => <li key={file.id}><Icon name="file" /><div className="file-description"><strong>{file.filename}</strong><span className="muted small">Added {sessionDate(file.created_at)}</span></div><button className="btn btn-secondary btn-small" disabled={busy === file.id} onClick={() => void download(file)}><Icon name="download" />{busy === file.id ? 'Downloading…' : 'Download'}</button></li>)}</ul></section>)}</div>}
  </section>;
}
