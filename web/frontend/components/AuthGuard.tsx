"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";

/**
 * Wrap any authenticated page's content with this. Redirects to /login
 * (preserving where the user was headed) once we know for certain there's
 * no session; shows a lightweight loading state while that's still unknown.
 */
export function AuthGuard({ children }: { children: React.ReactNode }) {
  const { session, loading, configured } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !session) {
      const next =
        typeof window !== "undefined"
          ? window.location.pathname + window.location.search
          : "/upload";
      router.replace(`/login?next=${encodeURIComponent(next)}`);
    }
  }, [loading, session, router]);

  if (!configured) {
    return (
      <div className="container-page py-16">
        <div className="card p-6 text-sm text-ink-200">
          Supabase isn&apos;t configured yet. Set{" "}
          <code className="text-signal-400">NEXT_PUBLIC_SUPABASE_URL</code> and{" "}
          <code className="text-signal-400">NEXT_PUBLIC_SUPABASE_ANON_KEY</code>{" "}
          to enable sign-in.
        </div>
      </div>
    );
  }

  if (loading || !session) {
    return (
      <div className="container-page py-16">
        <div className="flex flex-col items-center gap-3 py-24 text-center">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-ink-700 border-t-signal-500" />
          <p className="text-sm text-ink-400">Checking your session…</p>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
