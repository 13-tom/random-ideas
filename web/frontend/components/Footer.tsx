import Link from "next/link";
import { Logo } from "./Logo";

export function Footer() {
  return (
    <footer className="border-t border-ink-800/80">
      <div className="container-page flex flex-col items-start justify-between gap-6 py-10 sm:flex-row sm:items-center">
        <div className="flex flex-col gap-2">
          <Logo />
          <p className="max-w-sm text-sm text-ink-400">
            Turn long videos into short, scroll-stopping clips — automatically.
          </p>
        </div>
        <div className="flex items-center gap-6 text-sm text-ink-400">
          <Link href="/#how-it-works" className="hover:text-ink-100">
            How it works
          </Link>
          <Link href="/#pricing" className="hover:text-ink-100">
            Pricing
          </Link>
          <Link href="/login" className="hover:text-ink-100">
            Sign in
          </Link>
        </div>
      </div>
      <div className="border-t border-ink-800/80 py-5">
        <p className="container-page text-xs text-ink-500">
          &copy; {new Date().getFullYear()} kalakaar.io. All rights reserved.
        </p>
      </div>
    </footer>
  );
}
