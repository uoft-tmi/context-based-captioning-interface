import type { SessionSummary } from './api';

export function hasTranscript(session: SessionSummary): boolean { return Boolean(session.has_transcript || session.transcript_key) || session.transcript_text !== null; }

export function sessionStatus(session: SessionSummary): string {
  if (session.deleting_at) return 'Deletion pending';
  if (session.is_recording) return 'Recording';
  if (session.is_active) return 'Ready to record';
  if (hasTranscript(session)) return session.error ? 'Saved with issues' : 'Transcript saved';
  return session.error ? 'Ended with an issue' : 'Ended';
}
export const sessionDate = (value: string) => new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
export function recordingTime(ms: number): string {
  const seconds = Math.max(0, Math.floor(ms / 1000));
  return `${Math.floor(seconds / 60).toString().padStart(2, '0')}:${(seconds % 60).toString().padStart(2, '0')}`;
}
export function normalizeSessionName(name: string): string { return name.trim().replace(/\s+/g, ' '); }
export function saveDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url; link.download = filename; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
