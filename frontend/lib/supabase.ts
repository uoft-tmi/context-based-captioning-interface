import { createBrowserClient } from '@supabase/ssr'

const supabaseUrl = process.env.SUPABASE_URL ?? "";
const supabasePublishableKey = process.env.SUPABASE_PUBLISHABLE_KEY ?? "";

// Using createBrowserClient automatically syncs the Supabase user session strictly into secure HTTP cookies!
// This solves the Next.js Middleware blocking us because the server can finally see the login tokens.
export const supabase = createBrowserClient(
  supabaseUrl || "http://placeholder.invalid",
  supabasePublishableKey || "placeholder"
);
