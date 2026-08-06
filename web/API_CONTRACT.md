# kalakaar.io API contract (backend <-> frontend)

Auth: Supabase magic-link, handled entirely client-side in the Next.js app
(`@supabase/supabase-js`). The frontend sends the Supabase session's JWT as
`Authorization: Bearer <token>` on every request below; the backend verifies
it (does not issue its own tokens).

Base URL: `NEXT_PUBLIC_API_URL` env var in the frontend.

## POST /api/uploads
Request: `{ "filename": string, "content_type": string }`
Response: `{ "upload_id": string, "put_url": string, "r2_key": string }`
Frontend PUTs the raw file bytes directly to `put_url` (R2 presigned URL) -
does not go through the backend.

## POST /api/jobs
Request:
```json
{
  "upload_id": "string",
  "options": {
    "aspect": "original|vertical|square|portrait|landscape",
    "track_faces": boolean,
    "caption_style": "plain|word|highlight",
    "language": "en|hi|auto|hinglish",
    "min_duration": number,
    "max_duration": number,
    "max_clips": number
  }
}
```
Response: `{ "job_id": string }`

## GET /api/jobs
Response: `{ "jobs": [ { "id": string, "status": string, "created_at": string, "source_filename": string } ] }`

## GET /api/jobs/{id}
Response:
```json
{
  "id": "string",
  "status": "queued|transcribing|scoring|cutting|reframing|captioning|uploading|done|failed",
  "progress_pct": number,
  "error_message": "string|null",
  "created_at": "string"
}
```
Frontend polls this every 2-3s while status is not `done`/`failed`.

## GET /api/jobs/{id}/clips
Only meaningful once status is `done`.
Response:
```json
{
  "clips": [
    {
      "id": "string",
      "title": "string",
      "score": number,
      "duration": number,
      "download_url": "string",
      "preview_url": "string",
      "thumbnail_url": "string|null"
    }
  ]
}
```
`download_url`/`preview_url`/`thumbnail_url` are short-lived presigned R2 GET URLs.

## POST /internal/jobs/{id}/run
Internal only (called by the push-queue, e.g. Cloud Tasks), not by the
frontend. No response body contract the frontend needs to know about.

---
Status codes: 401 for missing/invalid auth, 404 for a job/upload not owned
by the caller (never leak existence of another user's job), 422 for
validation errors (standard FastAPI shape), 200/201 otherwise.
