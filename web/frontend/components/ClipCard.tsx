import type { Clip } from "@/lib/api";

function formatDuration(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export function ClipCard({ clip }: { clip: Clip }) {
  return (
    <div className="card group overflow-hidden">
      <div className="relative aspect-[9/16] bg-ink-900">
        <video
          src={clip.preview_url}
          poster={clip.thumbnail_url ?? undefined}
          controls
          preload="metadata"
          className="h-full w-full object-cover"
        />
        <div className="badge pointer-events-none absolute right-2 top-2 bg-ink-950/80 text-ink-100 backdrop-blur">
          {formatDuration(clip.duration)}
        </div>
      </div>

      <div className="p-4">
        <h3 className="line-clamp-2 font-display text-[15px] font-bold leading-snug text-ink-50">
          {clip.title}
        </h3>

        <div className="mt-2 flex items-center gap-1.5 text-sm text-ink-400">
          <svg viewBox="0 0 24 24" className="h-3.5 w-3.5 text-signal-500" fill="currentColor">
            <path d="M12 3l1.8 5.4L19 10l-5.2 1.6L12 17l-1.8-5.4L5 10l5.2-1.6L12 3z" />
          </svg>
          <span>{Math.round(clip.score)} hook score</span>
        </div>

        <a
          href={clip.download_url}
          download
          className="btn-secondary mt-4 w-full !py-2 text-sm"
        >
          <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={1.8}>
            <path d="M12 4v12M12 16l-4.5-4.5M12 16l4.5-4.5" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M4 18v1.5A1.5 1.5 0 005.5 21h13a1.5 1.5 0 001.5-1.5V18" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          Download
        </a>
      </div>
    </div>
  );
}
