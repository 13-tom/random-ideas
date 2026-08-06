"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AuthGuard } from "@/components/AuthGuard";
import { ApiError, listJobs, type JobSummary } from "@/lib/api";

const STATUS_STYLES: Record<string, string> = {
  done: "bg-emerald-500/15 text-emerald-400",
  failed: "bg-red-500/15 text-red-400",
  queued: "bg-ink-700 text-ink-300",
};

function statusStyle(status: string): string {
  return STATUS_STYLES[status] ?? "bg-signal-500/15 text-signal-400";
}

function JobsListContent() {
  const [jobs, setJobs] = useState<JobSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listJobs()
      .then(({ jobs }) => {
        if (!cancelled) setJobs(jobs);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(
            err instanceof ApiError ? err.message : "Couldn't load your jobs."
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="container-page py-12 sm:py-16">
      <div className="mx-auto max-w-4xl">
        <div className="mb-8 flex flex-wrap items-center justify-between gap-4">
          <h1 className="font-display text-3xl font-bold tracking-tight text-ink-50">
            Your jobs
          </h1>
          <Link href="/upload" className="btn-primary">
            New clip job
          </Link>
        </div>

        {error && (
          <div className="card p-6 text-sm text-signal-400">{error}</div>
        )}

        {!jobs && !error && (
          <div className="space-y-3">
            {[0, 1, 2].map((i) => (
              <div key={i} className="skeleton card h-20" />
            ))}
          </div>
        )}

        {jobs && jobs.length === 0 && (
          <div className="card flex flex-col items-center gap-3 px-6 py-16 text-center">
            <p className="text-ink-200">You haven&apos;t started any clip jobs yet.</p>
            <Link href="/upload" className="btn-primary">
              Upload your first video
            </Link>
          </div>
        )}

        {jobs && jobs.length > 0 && (
          <ul className="space-y-3">
            {jobs.map((job) => (
              <li key={job.id}>
                <Link
                  href={`/jobs/${job.id}`}
                  className="card flex items-center justify-between gap-4 px-5 py-4 transition-colors hover:border-ink-500"
                >
                  <div className="min-w-0">
                    <p className="truncate font-medium text-ink-100">
                      {job.source_filename}
                    </p>
                    <p className="mt-0.5 text-sm text-ink-400">
                      {new Date(job.created_at).toLocaleString()}
                    </p>
                  </div>
                  <span
                    className={`badge shrink-0 ${statusStyle(job.status)}`}
                  >
                    {job.status}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

export default function JobsPage() {
  return (
    <AuthGuard>
      <JobsListContent />
    </AuthGuard>
  );
}
