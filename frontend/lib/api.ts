import { supabase } from "./supabase";

const BACKEND_BASE_URL =
  process.env.NEXT_PUBLIC_BACKEND_BASE_URL ?? "http://localhost:8000";

export type ChunkMime = "audio/webm" | "audio/wav";

export interface SendChunkPayload {
  chunkIndex: number;
  audioB64: string;
  mime: ChunkMime;
}

export interface SendChunkResponse {
  partial_text: string;
}

async function getAuthHeaders(): Promise<Record<string, string>> {
  const {
    data: { session },
  } = await supabase.auth.getSession();
  const token = session?.access_token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request(
  path: string,
  options: RequestInit = {}
): Promise<Response> {
  const headers = {
    "Content-Type": "application/json",
    ...(await getAuthHeaders()),
    ...(options.headers as Record<string, string>),
  };
  return fetch(`${BACKEND_BASE_URL}${path}`, { ...options, headers });
}

// ---------- Session API ----------

export async function createSession(mode: "baseline" | "context") {
  const res = await request("/api/sessions", {
    method: "POST",
    body: JSON.stringify({ mode }),
  });
  return res.json();
}

export async function uploadNotes(sessionId: string, file: File) {
  const authHeaders = await getAuthHeaders();
  const form = new FormData();
  form.append("file", file);
  return fetch(`${BACKEND_BASE_URL}/api/sessions/${sessionId}/notes`, {
    method: "POST",
    headers: authHeaders,
    body: form,
  }).then((r) => r.json());
}

export async function startSession(sessionId: string) {
  const res = await request(`/api/sessions/${sessionId}/start`, {
    method: "POST",
  });
  return res.json();
}

export async function sendChunk(
  sessionId: string,
  payload: SendChunkPayload
): Promise<SendChunkResponse> {
  const res = await request(`/api/sessions/${sessionId}/chunks`, {
    method: "POST",
    body: JSON.stringify({
      chunk_index: payload.chunkIndex,
      audio_b64: payload.audioB64,
      mime: payload.mime,
    }),
  });

  const data = (await res.json()) as SendChunkResponse & { detail?: string };
  if (!res.ok) {
    throw new Error(data.detail ?? `Chunk upload failed with status ${res.status}`);
  }

  return data;
}

export async function stopSession(sessionId: string) {
  const res = await request(`/api/sessions/${sessionId}/stop`, {
    method: "POST",
  });
  return res.json();
}

export async function getSession(sessionId: string) {
  const res = await request(`/api/sessions/${sessionId}`);
  return res.json();
}

export async function downloadTranscript(sessionId: string) {
  const res = await request(`/api/sessions/${sessionId}/download`);
  return res.json();
}
