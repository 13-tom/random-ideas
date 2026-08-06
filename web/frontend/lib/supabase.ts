"use client";

import { createClient, type SupabaseClient } from "@supabase/supabase-js";

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

export const isSupabaseConfigured = Boolean(supabaseUrl && supabaseAnonKey);

let client: SupabaseClient | null = null;

/**
 * Lazily-created singleton browser client. Guarded so that a missing/invalid
 * env var (e.g. during a build, or a misconfigured preview deploy) surfaces
 * as a clear runtime warning instead of a hard crash on import.
 */
export function getSupabaseClient(): SupabaseClient | null {
  if (client) return client;
  if (!isSupabaseConfigured) {
    if (typeof window !== "undefined") {
      // eslint-disable-next-line no-console
      console.error(
        "Supabase is not configured: set NEXT_PUBLIC_SUPABASE_URL and " +
          "NEXT_PUBLIC_SUPABASE_ANON_KEY (see .env.local.example)."
      );
    }
    return null;
  }
  try {
    client = createClient(supabaseUrl as string, supabaseAnonKey as string, {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: true,
      },
    });
    return client;
  } catch (err) {
    // eslint-disable-next-line no-console
    console.error("Failed to initialize Supabase client:", err);
    return null;
  }
}
