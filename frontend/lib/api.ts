import { supabase } from './supabase';

export type SessionMode = 'baseline' | 'context';
export interface ProviderCapabilities {
  name: string;
  supports_pdf_notes: boolean;
  recommended_chunk_ms: number;
  initial_chunk_ms?: number | null;
  min_request_interval_ms?: number;
}
export interface SessionSummary {
  id: string;
  user_id: string;
  name: string;
  recording_limit_seconds: number;
  recorded_duration_ms: number;
  recording_started_at: string | null;
  deleting_at: string | null;
  is_recording: boolean;
  transcript_text: string | null;
  has_transcript?: boolean;
  mode: SessionMode;
  is_active: boolean;
  error: string | null;
  created_at: string;
  expires_at: string;
  finalized_at: string | null;
  transcript_key: string | null;
}

const configuredBase = (process.env.NEXT_PUBLIC_BACKEND_BASE_URL || 'http://localhost:8000').trim().replace(/\/+$/, '');
const backendBase = configuredBase.startsWith('/') || /^https?:\/\//i.test(configuredBase)
  ? configuredBase : `http://${configuredBase}`;

export function buildBackendUrl(path: string): string {
  return `${backendBase}${path}`;
}

async function accessToken(): Promise<string> {
  const { data: { session } } = await supabase.auth.getSession();
  if (!session) throw new Error('Please sign in again.');
  return session.access_token;
}

async function request(path: string, options: RequestInit = {}): Promise<Response> {
  const headers = new Headers(options.headers);
  headers.set('Authorization', `Bearer ${await accessToken()}`);
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json');
  let response: Response;
  try {
    response = await fetch(buildBackendUrl(path), { ...options, headers });
  } catch {
    throw new Error('We couldn’t reach the lecture service. Check your connection and try again.');
  }
  if (!response.ok) {
    if (response.status === 401) throw new Error('Your sign-in has expired. Please sign out and sign in again.');
    const body = await response.text();
    let detail = body || response.statusText;
    try { detail = JSON.parse(body).detail ?? detail; } catch { /* Non-JSON error. */ }
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
  }
  return response;
}

export async function createSession(mode: SessionMode, name: string): Promise<SessionSummary> {
  return (await request('/api/sessions', { method: 'POST', body: JSON.stringify({ mode, name }) })).json();
}
export async function getActiveSession(): Promise<SessionSummary | null> {
  return (await request('/api/sessions/active')).json();
}
export async function getProviderCapabilities(): Promise<ProviderCapabilities> {
  return (await request('/api/capabilities')).json();
}
export async function getSessionDetails(id: string): Promise<SessionSummary> {
  return (await request(`/api/sessions/${id}`)).json();
}
export async function listSessionNotes(id: string): Promise<string[]> {
  return (await request(`/api/sessions/${id}/notes`)).json();
}
export async function uploadSessionNote(id: string, file: File): Promise<void> {
  const body = new FormData();
  body.append('file', new Blob([file], { type: 'application/pdf' }), file.name);
  await request(`/api/sessions/${id}/notes`, { method: 'POST', body });
}
export async function endSession(id: string): Promise<void> {
  await request(`/api/sessions/${id}/end`, { method: 'POST' });
}
export async function downloadSessionPdf(id: string): Promise<Blob> {
  return (await request(`/api/sessions/${id}/download`)).blob();
}
export async function getSessionStreamUrlWithAuth(id: string): Promise<string> {
  const url = new URL(buildBackendUrl(`/ws/sessions/${id}/stream`), window.location.origin);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  url.searchParams.set('access_token', await accessToken());
  return url.toString();
}


export interface AccountOverview { plan: 'free' | 'paid'; recording_limit_seconds: number; }
export interface LibraryFile { id: string; session_id: string; session_name: string; filename: string; created_at: string; }
export async function listSessions(): Promise<SessionSummary[]> { return (await request('/api/sessions')).json(); }
export async function getAccount(): Promise<AccountOverview> { return (await request('/api/account')).json(); }
export async function listLibraryFiles(): Promise<LibraryFile[]> { return (await request('/api/library')).json(); }
export async function deleteSession(id: string): Promise<void> { await request(`/api/sessions/${id}`, { method: 'DELETE' }); }
export async function downloadSessionNote(id: string, filename: string): Promise<Blob> { return (await request(`/api/sessions/${id}/notes/${encodeURIComponent(filename)}`)).blob(); }
export async function deleteSessionNote(id: string, filename: string): Promise<void> { await request(`/api/sessions/${id}/notes/${encodeURIComponent(filename)}`, { method: 'DELETE' }); }
