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

const BACKEND_URL = normalizeBackendBaseUrl(
  process.env.NEXT_PUBLIC_BACKEND_BASE_URL,
);

/**
 * A wrapper around the native fetch API that automatically grabs the
 * current user's Supabase JWT access token and appends it to the
 * Authorization header for requests to the FastAPI backend.
 */
export async function fetchWithAuth(
  endpoint: string,
  options: RequestInit = {},
) {
  // 1. Retrieve the current user's session from Supabase
  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (!session) {
    throw new Error('UNAUTHORIZED: No active Supabase session found.');
  }

  // 2. Inject the JWT into the Authorization header
  const headers = new Headers(options.headers || {});
  headers.set('Authorization', `Bearer ${session.access_token}`);

  // Set default JSON Content-Type unless we are transmitting FormData (like PDF uploads)
  if (!headers.has('Content-Type') && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }

  // 3. Execute the fetch request to the configured backend URL
  const url = `${BACKEND_URL}${endpoint}`;
  const response = await fetch(url, {
    ...options,
    headers,
  });

  return response;
}
