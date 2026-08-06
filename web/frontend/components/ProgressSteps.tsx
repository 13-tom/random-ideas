import type { JobStatus } from "@/lib/api";

const STEPS: { status: JobStatus; label: string }[] = [
  { status: "transcribing", label: "Transcribing" },
  { status: "scoring", label: "Scoring clips" },
  { status: "cutting", label: "Cutting" },
  { status: "reframing", label: "Reframing" },
  { status: "captioning", label: "Captioning" },
  { status: "uploading", label: "Uploading" },
];

function stepIndex(status: JobStatus): number {
  if (status === "queued") return -1;
  if (status === "done") return STEPS.length;
  const i = STEPS.findIndex((s) => s.status === status);
  return i === -1 ? -1 : i;
}

export function ProgressSteps({
  status,
  progressPct,
}: {
  status: JobStatus;
  progressPct: number;
}) {
  const current = stepIndex(status);
  const failed = status === "failed";

  return (
    <div>
      <div className="mb-3 flex items-center justify-between text-sm">
        <span className="font-medium text-ink-100">
          {failed ? "Job failed" : status === "done" ? "All done" : "Processing"}
        </span>
        <span className="text-ink-400">{Math.round(progressPct)}%</span>
      </div>

      <div className="h-2 w-full overflow-hidden rounded-full bg-ink-800">
        <div
          className={`h-full rounded-full transition-[width] duration-500 ${
            failed ? "bg-red-500" : "bg-signal-500"
          }`}
          style={{ width: `${Math.max(4, Math.min(100, progressPct))}%` }}
        />
      </div>

      <ol className="mt-6 grid grid-cols-2 gap-x-4 gap-y-4 sm:grid-cols-3 lg:grid-cols-6">
        {STEPS.map((s, i) => {
          const isDone = current > i || status === "done";
          const isCurrent = current === i && status !== "done";
          return (
            <li key={s.status} className="flex items-center gap-2.5 lg:flex-col lg:items-start lg:gap-2">
              <span
                className={`grid h-6 w-6 shrink-0 place-items-center rounded-full text-[11px] font-semibold ${
                  failed && isCurrent
                    ? "bg-red-500/20 text-red-400"
                    : isDone
                    ? "bg-signal-500 text-ink-950"
                    : isCurrent
                    ? "border-2 border-signal-500 text-signal-400"
                    : "bg-ink-800 text-ink-500"
                }`}
              >
                {isDone ? (
                  <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth={3}>
                    <path d="M5 13l4 4L19 7" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                ) : (
                  i + 1
                )}
              </span>
              <span
                className={`text-xs font-medium ${
                  isDone || isCurrent ? "text-ink-100" : "text-ink-500"
                }`}
              >
                {s.label}
              </span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
