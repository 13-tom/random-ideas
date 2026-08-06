"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { AuthGuard } from "@/components/AuthGuard";
import { ProgressSteps } from "@/components/ProgressSteps";
import { ClipCard } from "@/components/ClipCard";
import { ApiError, getJob, getJobClips, type Clip, type JobDetail } from "@/lib/api";

const POLL_INTERVAL_MS = 2500;
const TERMINAL_STATUSES = new Set(["done", "failed"]);

function JobPageContent({ jobId }: { jobId: string }) {
  const [job, setJob] = useState<JobDetail | null>(null);
  const [clips, setClips] = useState<Clip[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [clipsError, setClipsError] = useState<string | null>(null);

  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const cancelledRef = useRef(false);

  useEffect(() => {
    cancelledRef.current = false;

    async function poll() {
      try {
        const detail = await getJob(jobId);
        if (cancelledRef.current) return;
        setJob(detail);
        setError(null);

        if (!TERMINAL_STATUSES.has(detail.status)) {
          timerRef.current = setTimeout(poll, POLL_INTERVAL_MS);
        } else if (detail.status === "done") {
          try {
            const { clips } = await getJobClips(jobId);
            if (!cancelledRef.current) setClips(clips);
          } catch (err) {
            if (!cancelledRef.current) {
              setClipsError(
                err instanceof ApiError ? err.message : "Couldn't load clips."
              );
            }
          }
        }
      } catch (err) {
        if (cancelledRef.current) return;
        setError(
          err instanceof ApiError ? err.message : "Couldn't load this job."
        );
        // Back off and keep trying — a transient network blip shouldn't
        // strand the user on an error screen forever.
        timerRef.current = setTimeout(poll, POLL_INTERVAL_MS);
      }
    }

    poll();

    return () => {
      cancelledRef.current = true;
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [jobId]);

  if (error && !job) {
    return (
      <div className="container-page py-16">
        <div className="card p-6">
          <p className="text-sm text-signal-400">{error}</p>
          <Link href="/jobs" className="btn-secondary mt-4 inline-flex">
            Back to jobs
          </Link>
        </div>
      </div>
    );
  }

  if (!job) {
    return (
      <div className="container-page py-16">
        <div className="flex flex-col items-center gap-3 py-24 text-center">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-ink-700 border-t-signal-500" />
          <p className="text-sm text-ink-400">Loading job…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="container-page py-12 sm:py-16">
      <div className="mx-auto max-w-5xl">
        <div className="mb-8 flex flex-wrap items-start justify-between gap-4">
          <div>
            <Link href="/jobs" className="text-sm text-ink-400 hover:text-ink-100">
              &larr; All jobs
            </Link>
            <h1 className="mt-2 font-display text-3xl font-bold tracking-tight text-ink-50">
              Job {job.id}
            </h1>
            <p className="mt-1 text-sm text-ink-400">
              Started {new Date(job.created_at).toLocaleString()}
            </p>
          </div>
        </div>

        <div className="card p-6 sm:p-8">
          <ProgressSteps status={job.status} progressPct={job.progress_pct} />

          {job.status === "failed" && (
            <div className="mt-6 rounded-xl border border-red-900/50 bg-red-950/30 p-4 text-sm text-red-300">
              {job.error_message || "This job failed. Please try uploading again."}
            </div>
          )}
        </div>

        {job.status === "done" && (
          <div className="mt-12">
            <h2 className="font-display text-2xl font-bold tracking-tight text-ink-50">
              Your clips
            </h2>

            {clipsError && (
              <p className="mt-3 text-sm text-signal-400">{clipsError}</p>
            )}

            {!clips && !clipsError && (
              <div className="mt-6 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
                {[0, 1, 2].map((i) => (
                  <div key={i} className="card overflow-hidden">
                    <div className="skeleton aspect-[9/16]" />
                    <div className="space-y-2 p-4">
                      <div className="skeleton h-4 w-3/4 rounded" />
                      <div className="skeleton h-4 w-1/2 rounded" />
                    </div>
                  </div>
                ))}
              </div>
            )}

            {clips && clips.length === 0 && (
              <p className="mt-6 text-sm text-ink-400">
                No clips were generated for this job.
              </p>
            )}

            {clips && clips.length > 0 && (
              <div className="mt-6 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
                {clips.map((clip) => (
                  <ClipCard key={clip.id} clip={clip} />
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default function JobPage() {
  const params = useParams<{ id: string }>();

  return (
    <AuthGuard>
      <JobPageContent jobId={params.id} />
    </AuthGuard>
  );
}
