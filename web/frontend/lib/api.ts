"use client";

/**
 * Thin typed client for the KatGai Reel backend, matching web/API_CONTRACT.md
 * exactly. No business logic lives here — callers get raw contract shapes
 * back and decide what to do with them.
 */

import { getSupabaseClient } from "./supabase";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

// ---- Contract types -------------------------------------------------

export type Aspect = "original" | "vertical" | "square" | "portrait" | "landscape";
export type CaptionStyle = "plain" | "word" | "highlight";
export type Language = "en" | "hi" | "auto" | "hinglish";

export interface JobOptions {
  aspect: Aspect;
  track_faces: boolean;
  caption_style: CaptionStyle;
  language: Language;
  min_duration: number;
  max_duration: number;
  max_clips: number;
}

export type JobStatus =
  | "queued"
  | "transcribing"
  | "scoring"
  | "cutting"
  | "reframing"
  | "captioning"
  | "uploading"
  | "done"
  | "failed";

export interface CreateUploadRequest {
  filename: string;
  content_type: string;
}

export interface CreateUploadResponse {
  upload_id: string;
  put_url: string;
  r2_key: string;
}

export interface CreateJobRequest {
  upload_id: string;
  options: JobOptions;
}

export interface CreateJobResponse {
  job_id: string;
}

export interface JobSummary {
  id: string;
  status: string;
  created_at: string;
  source_filename: string;
}

export interface ListJobsResponse {
  jobs: JobSummary[];
}

export interface JobDetail {
  id: string;
  status: JobStatus;
  progress_pct: number;
  error_message: string | null;
  created_at: string;
}

export interface Clip {
  id: string;
  title: string;
  score: number;
  duration: number;
  download_url: string;
  preview_url: string;
  thumbnail_url: string | null;
}

export interface ListClipsResponse {
  clips: Clip[];
}

// ---- Error type -------------------------------------------------------

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

// ---- Core request helper ----------------------------------------------

async function authHeader(): Promise<Record<string, string>> {
  const supabase = getSupabaseClient();
  if (!supabase) return {};
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request<T>(
  path: string,
  init?: RequestInit
): Promise<T> {
  if (!API_URL) {
    throw new ApiError(
      0,
      "NEXT_PUBLIC_API_URL is not set. See .env.local.example."
    );
  }

  const auth = await authHeader();
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...auth,
      ...(init?.headers ?? {}),
    },
  });

  if (!res.ok) {
    let detail: unknown = undefined;
    let message = `Request failed with status ${res.status}`;
    try {
      detail = await res.json();
      if (
        detail &&
        typeof detail === "object" &&
        "detail" in detail &&
        typeof (detail as { detail: unknown }).detail === "string"
      ) {
        message = (detail as { detail: string }).detail;
      }
    } catch {
      // response had no JSON body; keep the generic message
    }
    throw new ApiError(res.status, message, detail);
  }

  // 204 or empty body responses
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// ---- Endpoints ----------------------------------------------------------

/** POST /api/uploads */
export function createUpload(
  body: CreateUploadRequest
): Promise<CreateUploadResponse> {
  return request<CreateUploadResponse>("/api/uploads", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/**
 * PUTs the raw file bytes directly to the presigned R2 URL returned by
 * createUpload. Never proxied through the backend.
 */
export async function putFileToR2(
  putUrl: string,
  file: File,
  onProgress?: (pct: number) => void
): Promise<void> {
  // Use XHR instead of fetch so we can report upload progress for the UI.
  await new Promise<void>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", putUrl);
    xhr.setRequestHeader("Content-Type", file.type || "application/octet-stream");
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress(Math.round((e.loaded / e.total) * 100));
      }
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve();
      } else {
        reject(new ApiError(xhr.status, `Upload to storage failed (${xhr.status})`));
      }
    };
    xhr.onerror = () => reject(new ApiError(0, "Network error during upload"));
    xhr.send(file);
  });
}

/** POST /api/jobs */
export function createJob(body: CreateJobRequest): Promise<CreateJobResponse> {
  return request<CreateJobResponse>("/api/jobs", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** GET /api/jobs */
export function listJobs(): Promise<ListJobsResponse> {
  return request<ListJobsResponse>("/api/jobs");
}

/** GET /api/jobs/{id} */
export function getJob(id: string): Promise<JobDetail> {
  return request<JobDetail>(`/api/jobs/${encodeURIComponent(id)}`);
}

/** GET /api/jobs/{id}/clips */
export function getJobClips(id: string): Promise<ListClipsResponse> {
  return request<ListClipsResponse>(
    `/api/jobs/${encodeURIComponent(id)}/clips`
  );
}
