import { supabase } from './supabase';

const DEFAULT_BACKEND_BASE_URL = 'http://localhost:8000';

function normalizeBackendBaseUrl(raw: string | undefined): string {
  const value = (raw ?? '').trim();

  if (!value) {
    return DEFAULT_BACKEND_BASE_URL;
  }

  if (/^https?:\/\//i.test(value)) {
    return value.replace(/\/$/, '');
  }

  if (value.startsWith('/')) {
    return value.replace(/\/$/, '');
  }

  // Support host:port style config like "localhost:8000".
  return `http://${value.replace(/\/$/, '')}`;
}

const BACKEND_BASE_URL = normalizeBackendBaseUrl(
  process.env.NEXT_PUBLIC_BACKEND_BASE_URL,
);

function buildBackendUrl(path: string): string {
  if (BACKEND_BASE_URL.startsWith('/')) {
    return `${BACKEND_BASE_URL}${path}`;
  }

  return new URL(path, `${BACKEND_BASE_URL}/`).toString();
}

function toNetworkErrorMessage(error: unknown): string {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return 'Failed to fetch';
}

function toErrorString(value: unknown, fallback: string): string {
  if (typeof value === 'string' && value.trim().length > 0) {
    return value;
  }

  if (value instanceof Error && value.message.trim().length > 0) {
    return value.message;
  }

  if (value !== null && value !== undefined) {
    try {
      const serialized = JSON.stringify(value);
      if (serialized && serialized !== '{}') {
        return serialized;
      }
    } catch {
      // Ignore serialization errors and use fallback.
    }

    const asString = String(value);
    if (asString && asString !== '[object Object]') {
      return asString;
    }
  }

  return fallback;
}

export type SessionMode = 'baseline' | 'context';
export type ChunkMime = 'audio/webm' | 'audio/wav';

export interface SessionSummary {
  session_id: string;
  mode?: SessionMode;
  status?: string;
  created_at?: string;
  ended_at?: string | null;
}

export interface CreateSessionResponse {
  session_id: string;
  mode?: SessionMode;
  status?: string;
}

function resolveSessionId(data: unknown): string | null {
  if (!data || typeof data !== 'object') {
    return null;
  }

  const record = data as Record<string, unknown>;
  const directSessionId = record.session_id;
  const directId = record.id;
  const nestedSession = record.session as Record<string, unknown> | undefined;
  const nestedSessionId = nestedSession?.session_id;
  const nestedId = nestedSession?.id;

  const value =
    (typeof directSessionId === 'string' && directSessionId) ||
    (typeof directId === 'string' && directId) ||
    (typeof nestedSessionId === 'string' && nestedSessionId) ||
    (typeof nestedId === 'string' && nestedId) ||
    null;

  return value;
}

export interface SessionNote {
  filename: string;
  size_bytes?: number;
  uploaded_at?: string;
}

export interface SessionErrorPayload {
  reason: string;
  details?: string;
  source?: string;
}

export interface StreamChunkPayload {
  chunk_index: number;
  audio_b64: string;
  mime: ChunkMime;
  elapsed_ms?: number;
  created_at?: string;
  type?: 'audio_chunk';
}

export interface StreamServerMessage {
  partial_text?: string;
  text?: string;
  caption?: string;
  final_text?: string;
  is_final?: boolean;
  done?: boolean;
  error?: string;
  detail?: string;
}

export interface SendSessionChunkPayload {
  chunk_index: number;
  audio_b64: string;
  mime: ChunkMime;
  elapsed_ms?: number;
  created_at?: string;
}

export interface SendSessionChunkResponse {
  partial_text?: string;
  text?: string;
  caption?: string;
  final_text?: string;
  is_final?: boolean;
  done?: boolean;
  detail?: string;
  error?: string;
}

async function getAccessToken(): Promise<string | null> {
  const {
    data: { session },
  } = await supabase.auth.getSession();
  return session?.access_token ?? null;
}

async function request(
  path: string,
  options: RequestInit = {},
  withJsonContentType = true,
): Promise<Response> {
  const token = await getAccessToken();
  const headers = new Headers(options.headers ?? {});

  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  if (
    withJsonContentType &&
    !headers.has('Content-Type') &&
    !(options.body instanceof FormData)
  ) {
    headers.set('Content-Type', 'application/json');
  }

  const url = buildBackendUrl(path);

  try {
    return await fetch(url, {
      ...options,
      headers,
    });
  } catch (error) {
    const method = options.method ?? 'GET';
    throw new Error(
      `Network request failed (${method} ${url}). Verify backend availability, CORS policy, and NEXT_PUBLIC_BACKEND_BASE_URL. ${toNetworkErrorMessage(error)}`,
    );
  }
}

async function parseErrorMessage(res: Response): Promise<string> {
  try {
    const data = (await res.json()) as {
      detail?: unknown;
      message?: unknown;
      error?: unknown;
    };
    return toErrorString(
      data.detail ?? data.message ?? data.error,
      `${res.status} ${res.statusText}`,
    );
  } catch {
    try {
      const text = await res.text();
      return text || `${res.status} ${res.statusText}`;
    } catch {
      return `${res.status} ${res.statusText}`;
    }
  }
}

async function expectJson<T>(res: Response, context: string): Promise<T> {
  if (!res.ok) {
    const message = await parseErrorMessage(res);
    throw new Error(`${context}: ${message}`);
  }
  return (await res.json()) as T;
}

async function expectBlob(res: Response, context: string): Promise<Blob> {
  if (!res.ok) {
    const message = await parseErrorMessage(res);
    throw new Error(`${context}: ${message}`);
  }
  return res.blob();
}

async function parseJsonOrEmpty(
  res: Response,
): Promise<Record<string, unknown>> {
  try {
    return (await res.json()) as Record<string, unknown>;
  } catch {
    return {};
  }
}

export function getSessionStreamUrl(
  sessionId: string,
  accessToken?: string,
): string {
  const browserOrigin =
    typeof window !== 'undefined'
      ? window.location.origin
      : DEFAULT_BACKEND_BASE_URL;

  const wsBase = BACKEND_BASE_URL.startsWith('/')
    ? `${browserOrigin}${BACKEND_BASE_URL}`.replace(/^http/, 'ws')
    : BACKEND_BASE_URL.replace(/^http/, 'ws');
  const url = new URL(`/ws/sessions/${sessionId}/stream`, wsBase);

  if (accessToken) {
    url.searchParams.set('access_token', accessToken);
  }

  return url.toString();
}

export function getSessionStreamUrls(
  sessionId: string,
  accessToken?: string,
): string[] {
  const urls = new Set<string>();

  if (!accessToken) {
    return [];
  }

  const wsBase = BACKEND_BASE_URL.startsWith('/')
    ? `${typeof window !== 'undefined' ? window.location.origin : DEFAULT_BACKEND_BASE_URL}${BACKEND_BASE_URL}`.replace(
        /^http/,
        'ws',
      )
    : BACKEND_BASE_URL.replace(/^http/, 'ws');

  // Preferred for local FastAPI websocket auth path.
  const tokenUrl = new URL(`/ws/sessions/${sessionId}/stream`, wsBase);
  tokenUrl.searchParams.set('token', accessToken);
  urls.add(tokenUrl.toString());

  // Backward compatibility for servers expecting access_token.
  urls.add(getSessionStreamUrl(sessionId, accessToken));

  return Array.from(urls);
}

export async function getSessionStreamUrlWithAuth(
  sessionId: string,
): Promise<string> {
  const token = await getAccessToken();
  return getSessionStreamUrl(sessionId, token ?? undefined);
}

export async function getSessionStreamUrlsWithAuth(
  sessionId: string,
): Promise<string[]> {
  const token = await getAccessToken();
  if (!token) {
    throw new Error('Authentication required for websocket streaming.');
  }
  return getSessionStreamUrls(sessionId, token ?? undefined);
}

export async function sendSessionChunk(
  sessionId: string,
  payload: SendSessionChunkPayload,
): Promise<SendSessionChunkResponse> {
  const endpoints = [
    `/api/sessions/${sessionId}/chunks`,
    `/api/sessions/${sessionId}/chunk`,
  ];

  let lastMessage = 'Chunk upload failed.';

  for (const endpoint of endpoints) {
    const res = await request(endpoint, {
      method: 'POST',
      body: JSON.stringify(payload),
    });

    if (res.status === 404) {
      lastMessage = await parseErrorMessage(res);
      continue;
    }

    if (!res.ok) {
      const message = await parseErrorMessage(res);
      throw new Error(`Chunk upload failed: ${message}`);
    }

    return (await res.json()) as SendSessionChunkResponse;
  }

  throw new Error(`Chunk upload failed: ${lastMessage}`);
}

export async function getSessions(): Promise<SessionSummary[]> {
  const res = await request('/api/sessions', { method: 'GET' });
  return expectJson<SessionSummary[]>(res, 'Failed to fetch sessions');
}

export async function createSession(
  mode: SessionMode,
): Promise<CreateSessionResponse> {
  const res = await request('/api/sessions', {
    method: 'POST',
    body: JSON.stringify({ mode }),
  });

  const data = await expectJson<Record<string, unknown>>(
    res,
    'Failed to create session',
  );
  const sessionId = resolveSessionId(data);

  if (!sessionId) {
    throw new Error(
      'Failed to create session: backend response did not include a session id.',
    );
  }

  return {
    session_id: sessionId,
    mode: (data.mode as SessionMode | undefined) ?? mode,
    status: typeof data.status === 'string' ? data.status : undefined,
  };
}

export async function getActiveSession(): Promise<SessionSummary | null> {
  const res = await request('/api/sessions/active', { method: 'GET' });

  if (res.status === 404) {
    return null;
  }

  return expectJson<SessionSummary | null>(
    res,
    'Failed to fetch active session',
  );
}

export async function getSessionDetails(
  sessionId: string,
): Promise<SessionSummary> {
  const res = await request(`/api/sessions/${sessionId}`, { method: 'GET' });
  return expectJson<SessionSummary>(res, 'Failed to fetch session details');
}

export async function listSessionNotes(
  sessionId: string,
): Promise<SessionNote[]> {
  const res = await request(`/api/sessions/${sessionId}/notes`, {
    method: 'GET',
  });
  return expectJson<SessionNote[]>(res, 'Failed to list session notes');
}

export async function uploadSessionNote(
  sessionId: string,
  file: File,
): Promise<SessionNote | Record<string, unknown>> {
  const pdfFileForm = new FormData();
  pdfFileForm.append('pdf_file', file, file.name);

  let res = await request(
    `/api/sessions/${sessionId}/notes`,
    {
      method: 'POST',
      body: pdfFileForm,
    },
    false,
  );

  if (!res.ok) {
    const initialError = await parseErrorMessage(res);
    const lowerError = toErrorString(initialError, '').toLowerCase();
    const maybeWrongFieldName =
      lowerError.includes('field required') || lowerError.includes('pdf_file');

    if (maybeWrongFieldName) {
      const fileForm = new FormData();
      fileForm.append('file', file, file.name);

      res = await request(
        `/api/sessions/${sessionId}/notes`,
        {
          method: 'POST',
          body: fileForm,
        },
        false,
      );

      if (!res.ok) {
        const fallbackError = await parseErrorMessage(res);
        throw new Error(
          `Failed to upload session note: ${fallbackError} (initial attempt: ${initialError})`,
        );
      }

      return (await res.json()) as SessionNote | Record<string, unknown>;
    }

    throw new Error(`Failed to upload session note: ${initialError}`);
  }

  return (await res.json()) as SessionNote | Record<string, unknown>;
}

export async function deleteSessionNote(
  sessionId: string,
  filename: string,
): Promise<void> {
  const res = await request(
    `/api/sessions/${sessionId}/notes/${encodeURIComponent(filename)}`,
    { method: 'DELETE' },
  );

  if (!res.ok) {
    const message = await parseErrorMessage(res);
    throw new Error(`Failed to delete note: ${message}`);
  }
}

export async function downloadSessionNote(
  sessionId: string,
  filename: string,
): Promise<Blob> {
  const res = await request(
    `/api/sessions/${sessionId}/notes/${encodeURIComponent(filename)}`,
    { method: 'GET' },
    false,
  );
  return expectBlob(res, 'Failed to download note');
}

export async function endSession(
  sessionId: string,
): Promise<Record<string, unknown>> {
  const res = await request(`/api/sessions/${sessionId}/end`, {
    method: 'POST',
  });

  if (!res.ok) {
    const message = await parseErrorMessage(res);
    throw new Error(`Failed to end session: ${message}`);
  }

  return parseJsonOrEmpty(res);
}

export async function markSessionError(
  sessionId: string,
  payload: SessionErrorPayload,
): Promise<Record<string, unknown>> {
  const endpoints = [
    `/api/sessions/${sessionId}/error`,
    `/api/sessions/${sessionId}/errors`,
  ];

  let lastNotFoundMessage: string | null = null;

  for (const endpoint of endpoints) {
    const res = await request(endpoint, {
      method: 'POST',
      body: JSON.stringify(payload),
    });

    if (res.status === 404) {
      lastNotFoundMessage = await parseErrorMessage(res);
      continue;
    }

    if (!res.ok) {
      const message = await parseErrorMessage(res);
      throw new Error(`Failed to mark session as error: ${message}`);
    }

    return parseJsonOrEmpty(res);
  }

  try {
    const ended = await endSession(sessionId);
    return {
      ...ended,
      error_fallback: true,
      reason: 'error-endpoint-missing',
      detail: lastNotFoundMessage ?? 'Error endpoint not found.',
    };
  } catch (fallbackError) {
    const fallbackMessage = toErrorString(
      fallbackError,
      'Unable to mark session as error or end session.',
    );
    throw new Error(
      `Failed to mark session as error: ${lastNotFoundMessage ?? 'Not Found'}. Fallback end also failed: ${fallbackMessage}`,
    );
  }
}

export async function downloadSessionPdf(sessionId: string): Promise<Blob> {
  const res = await request(`/api/sessions/${sessionId}/download`, {
    method: 'GET',
  });
  return expectBlob(res, 'Failed to download session PDF');
}

export async function healthCheck(): Promise<Record<string, unknown>> {
  const url = buildBackendUrl('/health');
  let res: Response;

  try {
    res = await fetch(url, { method: 'GET' });
  } catch (error) {
    throw new Error(
      `Health check request failed (GET ${url}). ${toNetworkErrorMessage(error)}`,
    );
  }

  return expectJson<Record<string, unknown>>(res, 'Health check failed');
}
