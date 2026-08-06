"use client";

import { useCallback, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { AuthGuard } from "@/components/AuthGuard";
import {
  ApiError,
  createJob,
  createUpload,
  putFileToR2,
  type Aspect,
  type CaptionStyle,
  type JobOptions,
  type Language,
} from "@/lib/api";

const DEFAULT_OPTIONS: JobOptions = {
  aspect: "vertical",
  track_faces: true,
  caption_style: "highlight",
  language: "auto",
  min_duration: 15,
  max_duration: 60,
  max_clips: 10,
};

const ASPECT_LABELS: Record<Aspect, string> = {
  original: "Original (keep source ratio)",
  vertical: "Vertical 9:16 (Reels/TikTok/Shorts)",
  square: "Square 1:1",
  portrait: "Portrait 4:5",
  landscape: "Landscape 16:9",
};

const CAPTION_LABELS: Record<CaptionStyle, string> = {
  plain: "Plain subtitles",
  word: "Word-by-word reveal",
  highlight: "Highlighted keywords",
};

const LANGUAGE_LABELS: Record<Language, string> = {
  auto: "Auto-detect",
  en: "English",
  hi: "Hindi",
  hinglish: "Hinglish (mixed)",
};

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let val = bytes / 1024;
  let i = 0;
  while (val >= 1024 && i < units.length - 1) {
    val /= 1024;
    i++;
  }
  return `${val.toFixed(1)} ${units[i]}`;
}

function UploadPageContent() {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [file, setFile] = useState<File | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [options, setOptions] = useState<JobOptions>(DEFAULT_OPTIONS);

  const [phase, setPhase] = useState<"idle" | "uploading" | "creating-job" | "error">(
    "idle"
  );
  const [uploadPct, setUploadPct] = useState(0);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const busy = phase === "uploading" || phase === "creating-job";

  const onFiles = useCallback((files: FileList | null) => {
    const f = files?.[0];
    if (!f) return;
    if (!f.type.startsWith("video/")) {
      setErrorMsg("Please select a video file.");
      return;
    }
    setErrorMsg(null);
    setFile(f);
  }, []);

  function updateOption<K extends keyof JobOptions>(key: K, value: JobOptions[K]) {
    setOptions((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) {
      setErrorMsg("Choose a video to upload first.");
      return;
    }
    if (options.min_duration > options.max_duration) {
      setErrorMsg("Minimum clip duration can't be greater than the maximum.");
      return;
    }

    setErrorMsg(null);
    try {
      setPhase("uploading");
      setUploadPct(0);
      const { upload_id, put_url } = await createUpload({
        filename: file.name,
        content_type: file.type || "application/octet-stream",
      });

      await putFileToR2(put_url, file, setUploadPct);

      setPhase("creating-job");
      const { job_id } = await createJob({ upload_id, options });

      router.push(`/jobs/${job_id}`);
    } catch (err) {
      setPhase("error");
      setErrorMsg(
        err instanceof ApiError
          ? err.message
          : "Something went wrong starting the job. Please try again."
      );
    }
  }

  return (
    <div className="container-page py-12 sm:py-16">
      <div className="mx-auto max-w-2xl">
        <h1 className="font-display text-3xl font-bold tracking-tight text-ink-50">
          New clip job
        </h1>
        <p className="mt-2 text-[15px] text-ink-300">
          Upload a video and tell us how you want the clips cut.
        </p>

        <form onSubmit={handleSubmit} className="mt-10 space-y-10">
          {/* -------------------------------------------------- File drop */}
          <div>
            <label className="field-label">Source video</label>
            <div
              role="button"
              tabIndex={0}
              onClick={() => fileInputRef.current?.click()}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") fileInputRef.current?.click();
              }}
              onDragOver={(e) => {
                e.preventDefault();
                setDragActive(true);
              }}
              onDragLeave={() => setDragActive(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragActive(false);
                onFiles(e.dataTransfer.files);
              }}
              className={`flex cursor-pointer flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed px-6 py-12 text-center transition-colors ${
                dragActive
                  ? "border-signal-500 bg-signal-500/5"
                  : "border-ink-600 hover:border-ink-500"
              }`}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept="video/*"
                className="sr-only"
                onChange={(e) => onFiles(e.target.files)}
                disabled={busy}
              />
              <div className="grid h-12 w-12 place-items-center rounded-full bg-ink-800 text-signal-400">
                <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth={1.6}>
                  <path d="M12 16V4M12 4l-4.5 4.5M12 4l4.5 4.5" strokeLinecap="round" strokeLinejoin="round" />
                  <path d="M4 16v2.5A1.5 1.5 0 005.5 20h13a1.5 1.5 0 001.5-1.5V16" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </div>
              {file ? (
                <div>
                  <p className="font-medium text-ink-100">{file.name}</p>
                  <p className="mt-0.5 text-sm text-ink-400">{formatBytes(file.size)}</p>
                </div>
              ) : (
                <div>
                  <p className="font-medium text-ink-100">
                    Drag a video here, or click to browse
                  </p>
                  <p className="mt-0.5 text-sm text-ink-400">MP4, MOV, MKV — any length</p>
                </div>
              )}
            </div>
          </div>

          {/* ------------------------------------------------------ Options */}
          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
            <div>
              <label htmlFor="aspect" className="field-label">
                Aspect ratio
              </label>
              <select
                id="aspect"
                className="field-select"
                value={options.aspect}
                disabled={busy}
                onChange={(e) => updateOption("aspect", e.target.value as Aspect)}
              >
                {(Object.keys(ASPECT_LABELS) as Aspect[]).map((v) => (
                  <option key={v} value={v}>
                    {ASPECT_LABELS[v]}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label htmlFor="caption_style" className="field-label">
                Caption style
              </label>
              <select
                id="caption_style"
                className="field-select"
                value={options.caption_style}
                disabled={busy}
                onChange={(e) => updateOption("caption_style", e.target.value as CaptionStyle)}
              >
                {(Object.keys(CAPTION_LABELS) as CaptionStyle[]).map((v) => (
                  <option key={v} value={v}>
                    {CAPTION_LABELS[v]}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label htmlFor="language" className="field-label">
                Spoken language
              </label>
              <select
                id="language"
                className="field-select"
                value={options.language}
                disabled={busy}
                onChange={(e) => updateOption("language", e.target.value as Language)}
              >
                {(Object.keys(LANGUAGE_LABELS) as Language[]).map((v) => (
                  <option key={v} value={v}>
                    {LANGUAGE_LABELS[v]}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label htmlFor="max_clips" className="field-label">
                Max clips to generate
              </label>
              <input
                id="max_clips"
                type="number"
                min={1}
                max={50}
                className="field-input"
                value={options.max_clips}
                disabled={busy}
                onChange={(e) => updateOption("max_clips", Number(e.target.value))}
              />
            </div>

            <div>
              <label htmlFor="min_duration" className="field-label">
                Min clip duration (sec)
              </label>
              <input
                id="min_duration"
                type="number"
                min={3}
                max={600}
                className="field-input"
                value={options.min_duration}
                disabled={busy}
                onChange={(e) => updateOption("min_duration", Number(e.target.value))}
              />
            </div>

            <div>
              <label htmlFor="max_duration" className="field-label">
                Max clip duration (sec)
              </label>
              <input
                id="max_duration"
                type="number"
                min={3}
                max={600}
                className="field-input"
                value={options.max_duration}
                disabled={busy}
                onChange={(e) => updateOption("max_duration", Number(e.target.value))}
              />
            </div>

            <div className="sm:col-span-2">
              <label className="flex items-center gap-3 rounded-xl border border-ink-600 bg-ink-900 px-4 py-3">
                <input
                  type="checkbox"
                  className="h-5 w-5 rounded border-ink-500 bg-ink-800 text-signal-500 focus:ring-signal-500"
                  checked={options.track_faces}
                  disabled={busy}
                  onChange={(e) => updateOption("track_faces", e.target.checked)}
                />
                <span>
                  <span className="block font-medium text-ink-100">Track faces while reframing</span>
                  <span className="block text-sm text-ink-400">
                    Keep the crop centered on whoever&apos;s speaking instead of a fixed frame.
                  </span>
                </span>
              </label>
            </div>
          </div>

          {phase === "uploading" && (
            <div>
              <div className="mb-2 flex items-center justify-between text-sm text-ink-300">
                <span>Uploading video…</span>
                <span>{uploadPct}%</span>
              </div>
              <div className="h-2 w-full overflow-hidden rounded-full bg-ink-800">
                <div
                  className="h-full rounded-full bg-signal-500 transition-[width] duration-300"
                  style={{ width: `${uploadPct}%` }}
                />
              </div>
            </div>
          )}

          {errorMsg && (
            <p role="alert" className="text-sm text-signal-400">
              {errorMsg}
            </p>
          )}

          <button type="submit" className="btn-primary w-full" disabled={busy || !file}>
            {phase === "uploading"
              ? "Uploading…"
              : phase === "creating-job"
              ? "Starting job…"
              : "Start clipping"}
          </button>
        </form>
      </div>
    </div>
  );
}

export default function UploadPage() {
  return (
    <AuthGuard>
      <UploadPageContent />
    </AuthGuard>
  );
}
