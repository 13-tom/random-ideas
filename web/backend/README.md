# KatGai Reel backend

FastAPI service that wraps the `ffmpeg-bulk-cutter/` pipeline as a web API.
See `../API_CONTRACT.md` for the exact request/response shapes the
frontend depends on.

## Local dev

```
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -r ../../ffmpeg-bulk-cutter/requirements.txt
pip install -r ../../ffmpeg-bulk-cutter/requirements-scoring.txt

# optional: Postgres + MinIO instead of the SQLite/no-storage defaults
docker compose -f ../docker-compose.dev.yml up -d
export DATABASE_URL=postgresql://katgaireel:katgaireel@localhost:5432/katgaireel

uvicorn app.main:app --reload
```

Without `DATABASE_URL`/`R2_*` set, it runs against a local SQLite file and
MinIO defaults from `app/config.py` - fine for exercising the API shape,
but uploads/downloads need either MinIO running at `localhost:9000` or
real R2 credentials.

## Architecture notes

- **Auth**: verifies a Supabase-issued JWT (`app/auth.py`) - this service
  never issues its own tokens or handles login.
- **Uploads/downloads never proxy through this process** - `app/storage.py`
  issues presigned R2 URLs; the frontend PUTs/GETs directly against R2.
- **Two ways a job's source video shows up**: a direct file upload (R2,
  presigned URL) or a YouTube link - the backend downloads that one itself
  via `yt-dlp`, inside the background job (`app/pipeline_runner.py`'s
  `_download_youtube`), not the request that creates the job. Either way,
  `generate_timestamps.py`/`run_pipeline.py` downstream just see a local
  file path.
- **Video processing runs as subprocesses** of the existing, unmodified
  `generate_timestamps.py` / `run_pipeline.py` CLI scripts
  (`app/pipeline_runner.py`), not as in-process library calls - see the
  module docstring for why.
- **Queue** (`app/queue.py`): push-based. `LocalQueue` fires the internal
  endpoint from a plain background thread (dev/single-instance) - not
  `asyncio.create_task`, which doesn't work here since FastAPI runs sync
  route handlers in a worker thread with no running event loop.
  `CloudTasksQueue` enqueues a real Cloud Tasks push task for scale-to-zero
  production deployment. Swap with `QUEUE_BACKEND` in `.env`.
- **Clip scoring provider** (OpenRouter vs. a local/self-hosted model) is
  chosen in `ffmpeg-bulk-cutter/clip_scoring.py`, passed through via
  `CLIP_SCORING_PROVIDER` - the backend doesn't hardcode which LLM is used.

## Deploying (Render)

`../../render.yaml` is a Render Blueprint - in the Render dashboard, "New +"
-> "Blueprint", point it at this repo, and it builds `Dockerfile` with the
repo root as build context (needed so it can also `COPY ffmpeg-bulk-cutter/`
- see the Dockerfile's own comment). Render prompts for each secret
(`DATABASE_URL`, `SUPABASE_URL`, `R2_*`, `OPENROUTER_API_KEY`) once in its
dashboard rather than storing them in the repo - use the values from your
local `.env`. Set `INTERNAL_BASE_URL` to this same service's own Render URL
once you know it (e.g. `https://katgaireel-backend.onrender.com`) - the
queue calls back into the service itself.

Free-tier caveat worth knowing going in: 512MB RAM / shared CPU is enough
to prove the app works end-to-end, but real videos (Whisper transcription +
ffmpeg encoding) will be slow and may hit memory limits on longer source
videos. Fine for testing, not a promise it'll handle anything you throw at it.
