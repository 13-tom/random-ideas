"use client";

import Link from "next/link";
import { useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { Logo } from "./Logo";

export function Navbar() {
  const { session, loading, signOut } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const authed = Boolean(session);

  return (
    <header className="sticky top-0 z-50 border-b border-ink-800/80 bg-ink-950/85 backdrop-blur-md">
      <div className="container-page flex h-16 items-center justify-between">
        <Link href="/" className="shrink-0" onClick={() => setMenuOpen(false)}>
          <Logo />
        </Link>

        <nav className="hidden items-center gap-1 md:flex">
          <Link href="/#how-it-works" className="btn-ghost !px-4 !py-2 text-[15px]">
            How it works
          </Link>
          <Link href="/#pricing" className="btn-ghost !px-4 !py-2 text-[15px]">
            Pricing
          </Link>
          {authed && (
            <Link href="/jobs" className="btn-ghost !px-4 !py-2 text-[15px]">
              My clips
            </Link>
          )}
        </nav>

        <div className="hidden items-center gap-3 md:flex">
          {loading ? (
            <div className="h-9 w-24 rounded-full skeleton" />
          ) : authed ? (
            <>
              <Link href="/upload" className="btn-primary !px-5 !py-2.5 text-sm">
                New clip job
              </Link>
              <button onClick={() => signOut()} className="btn-ghost !px-4 !py-2 text-sm">
                Sign out
              </button>
            </>
          ) : (
            <>
              <Link href="/login" className="btn-ghost !px-4 !py-2 text-sm">
                Sign in
              </Link>
              <Link href="/login" className="btn-primary !px-5 !py-2.5 text-sm">
                Get started
              </Link>
            </>
          )}
        </div>

        <button
          className="grid h-10 w-10 place-items-center rounded-lg text-ink-100 md:hidden"
          aria-label={menuOpen ? "Close menu" : "Open menu"}
          aria-expanded={menuOpen}
          onClick={() => setMenuOpen((v) => !v)}
        >
          <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth={1.75}>
            {menuOpen ? (
              <path d="M6 6l12 12M18 6L6 18" strokeLinecap="round" />
            ) : (
              <path d="M4 7h16M4 12h16M4 17h16" strokeLinecap="round" />
            )}
          </svg>
        </button>
      </div>

      {menuOpen && (
        <div className="border-t border-ink-800 bg-ink-950 px-5 pb-5 pt-2 md:hidden">
          <div className="flex flex-col gap-1">
            <Link href="/#how-it-works" className="btn-ghost justify-start" onClick={() => setMenuOpen(false)}>
              How it works
            </Link>
            <Link href="/#pricing" className="btn-ghost justify-start" onClick={() => setMenuOpen(false)}>
              Pricing
            </Link>
            {authed && (
              <Link href="/jobs" className="btn-ghost justify-start" onClick={() => setMenuOpen(false)}>
                My clips
              </Link>
            )}
            <div className="mt-2 flex flex-col gap-2 border-t border-ink-800 pt-3">
              {authed ? (
                <>
                  <Link href="/upload" className="btn-primary" onClick={() => setMenuOpen(false)}>
                    New clip job
                  </Link>
                  <button
                    onClick={() => {
                      setMenuOpen(false);
                      signOut();
                    }}
                    className="btn-secondary"
                  >
                    Sign out
                  </button>
                </>
              ) : (
                <>
                  <Link href="/login" className="btn-secondary" onClick={() => setMenuOpen(false)}>
                    Sign in
                  </Link>
                  <Link href="/login" className="btn-primary" onClick={() => setMenuOpen(false)}>
                    Get started
                  </Link>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </header>
  );
}
