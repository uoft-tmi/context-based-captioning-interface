import type { SessionSummary } from './api';

type DeletionTarget = Pick<SessionSummary, 'id' | 'name' | 'is_recording'>;

// Keep requests sequential so deleting a large library does not overwhelm storage.
// The server also checks ownership and recording leases for every deletion.
export async function deleteSessionBatch(
  sessions: readonly DeletionTarget[],
  remove: (id: string) => Promise<void>,
) {
  const deleted: string[] = [];
  const failed: { id: string; name: string; message: string }[] = [];
  const skipped: string[] = [];
  const seen = new Set<string>();
  for (const session of sessions) {
    if (seen.has(session.id)) continue;
    seen.add(session.id);
    if (session.is_recording) { skipped.push(session.id); continue; }
    try { await remove(session.id); deleted.push(session.id); }
    catch (error) {
      failed.push({ id: session.id, name: session.name, message: error instanceof Error ? error.message : 'Deletion failed.' });
    }
  }
  return { deleted, failed, skipped };
}
