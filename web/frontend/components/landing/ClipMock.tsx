/** Pure-CSS stand-in for a reframed, captioned vertical clip — no real
 * video asset needed for the marketing page, but reads clearly as one. */
export function ClipMock() {
  return (
    <div className="relative mx-auto w-full max-w-[280px]">
      {/* two faint clips stacked behind, hinting "many clips generated" */}
      <div className="absolute -right-6 top-6 h-full w-full -rotate-6 rounded-[28px] bg-ink-800/70 ring-1 ring-ink-700" />
      <div className="absolute -left-5 top-3 h-full w-full rotate-3 rounded-[28px] bg-ink-800/50 ring-1 ring-ink-700" />

      <div className="relative aspect-[9/16] overflow-hidden rounded-[28px] bg-ink-900 ring-1 ring-ink-600 shadow-2xl shadow-black/50">
        {/* "footage" */}
        <div className="absolute inset-0 bg-[radial-gradient(80%_60%_at_30%_20%,#3a2a4a_0%,#141621_60%),radial-gradient(70%_50%_at_80%_80%,#1c3a3a_0%,transparent_60%)]" />
        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-transparent to-black/70" />

        {/* score badge */}
        <div className="badge absolute left-3 top-3 border border-signal-500/40 bg-ink-950/80 text-signal-400 backdrop-blur">
          <span className="h-1.5 w-1.5 rounded-full bg-signal-500" />
          92 hook score
        </div>

        {/* duration badge */}
        <div className="badge absolute right-3 top-3 bg-ink-950/70 text-ink-200 backdrop-blur">
          0:34
        </div>

        {/* simulated face-tracked subject */}
        <div className="absolute left-1/2 top-[38%] h-24 w-24 -translate-x-1/2 rounded-full border-2 border-dashed border-white/25" />

        {/* burned-in captions, word-highlight style */}
        <div className="absolute inset-x-0 bottom-8 px-4 text-center">
          <p className="font-display text-xl font-bold leading-tight text-white drop-shadow-[0_2px_8px_rgba(0,0,0,0.8)]">
            this is the part{" "}
            <span className="rounded-md bg-signal-500 px-1.5 py-0.5 text-ink-950">
              everyone
            </span>{" "}
            clips
          </p>
        </div>
      </div>
    </div>
  );
}
