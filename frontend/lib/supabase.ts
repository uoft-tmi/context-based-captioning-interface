import { createBrowserClient } from '@supabase/ssr'

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "";

// Using createBrowserClient automatically syncs the Supabase user session strictly into secure HTTP cookies!
// This solves the Next.js Middleware blocking us because the server can finally see the login tokens.
export const supabase = createBrowserClient(
  supabaseUrl || "http://placeholder.invalid",
  supabaseAnonKey || "placeholder"
);
