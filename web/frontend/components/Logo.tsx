export function Logo({ className = "" }: { className?: string }) {
  return (
    <span
      className={`inline-flex items-center gap-2 font-display text-lg font-bold tracking-tight text-ink-50 ${className}`}
    >
      <span
        aria-hidden
        className="grid h-7 w-7 place-items-center rounded-lg bg-signal-500 text-ink-950"
      >
        <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none">
          <path
            d="M6 4.5v15l13-7.5-13-7.5z"
            fill="currentColor"
          />
        </svg>
      </span>
      kalakaar<span className="text-signal-500">.io</span>
    </span>
  );
}
