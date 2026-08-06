"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { getSupabaseClient, isSupabaseConfigured } from "@/lib/supabase";
import { useAuth } from "@/lib/auth-context";

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const { session, loading: sessionLoading } = useAuth();
  const next = params.get("next") || "/upload";

  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<"idle" | "sending" | "sent" | "error">(
    "idle"
  );
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    if (!sessionLoading && session) {
      router.replace(next);
    }
  }, [sessionLoading, session, router, next]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setErrorMsg(null);

    const supabase = getSupabaseClient();
    if (!supabase) {
      setStatus("error");
      setErrorMsg("Supabase isn't configured. See .env.local.example.");
      return;
    }

    setStatus("sending");
    const redirectTo =
      typeof window !== "undefined"
        ? `${window.location.origin}${next}`
        : undefined;

    const { error } = await supabase.auth.signInWithOtp({
      email,
      options: { emailRedirectTo: redirectTo },
    });

    if (error) {
      setStatus("error");
      setErrorMsg(error.message);
    } else {
      setStatus("sent");
    }
  }

  return (
    <div className="container-page flex min-h-[calc(100vh-4rem-14rem)] items-center py-16">
      <div className="mx-auto w-full max-w-md">
        <h1 className="font-display text-3xl font-bold tracking-tight text-ink-50">
          Sign in to kalakaar.io
        </h1>
        <p className="mt-2 text-[15px] text-ink-300">
          We&apos;ll email you a magic link — no password to remember.
        </p>

        {!isSupabaseConfigured && (
          <div className="mt-6 card border-signal-700/50 bg-signal-500/5 p-4 text-sm text-signal-400">
            Supabase isn&apos;t configured for this deploy yet
            (<code>NEXT_PUBLIC_SUPABASE_URL</code> /{" "}
            <code>NEXT_PUBLIC_SUPABASE_ANON_KEY</code> are missing).
          </div>
        )}

        {status === "sent" ? (
          <div className="mt-8 card p-6">
            <div className="mb-3 grid h-10 w-10 place-items-center rounded-full bg-signal-500/10 text-signal-400">
              <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth={1.8}>
                <path d="M3 7l9 6 9-6M4 5h16a1 1 0 011 1v12a1 1 0 01-1 1H4a1 1 0 01-1-1V6a1 1 0 011-1z" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
            <h2 className="font-display text-lg font-bold text-ink-50">Check your inbox</h2>
            <p className="mt-1.5 text-[15px] text-ink-300">
              We sent a sign-in link to <span className="text-ink-100">{email}</span>.
              Open it on this device to continue.
            </p>
            <button
              className="btn-ghost mt-5 !px-0 text-sm text-ink-400 hover:text-ink-100"
              onClick={() => setStatus("idle")}
            >
              Use a different email
            </button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="mt-8 space-y-5">
            <div>
              <label htmlFor="email" className="field-label">
                Email address
              </label>
              <input
                id="email"
                type="email"
                required
                autoComplete="email"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="field-input"
                disabled={!isSupabaseConfigured || status === "sending"}
              />
            </div>

            {status === "error" && errorMsg && (
              <p role="alert" className="text-sm text-signal-400">
                {errorMsg}
              </p>
            )}

            <button
              type="submit"
              className="btn-primary w-full"
              disabled={!isSupabaseConfigured || status === "sending"}
            >
              {status === "sending" ? "Sending link…" : "Send magic link"}
            </button>
          </form>
        )}

        <p className="mt-8 text-sm text-ink-500">
          By continuing you agree this is a demo/MVP build of kalakaar.io.{" "}
          <Link href="/" className="text-ink-300 underline underline-offset-2 hover:text-ink-100">
            Back to home
          </Link>
        </p>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginForm />
    </Suspense>
  );
}
