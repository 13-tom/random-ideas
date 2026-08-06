# kalakaar.io backend

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
export DATABASE_URL=postgresql://kalakaar:kalakaar@localhost:5432/kalakaar

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
- **Video processing runs as subprocesses** of the existing, unmodified
  `generate_timestamps.py` / `run_pipeline.py` CLI scripts
  (`app/pipeline_runner.py`), not as in-process library calls - see the
  module docstring for why.
- **Queue** (`app/queue.py`): push-based. `LocalQueue` fires the internal
  endpoint in-process (dev/single-instance); `CloudTasksQueue` enqueues a
  real Cloud Tasks push task for scale-to-zero production deployment.
  Swap with `QUEUE_BACKEND` in `.env`.
- **Clip scoring provider** (OpenRouter vs. a local/self-hosted model) is
  chosen in `ffmpeg-bulk-cutter/clip_scoring.py`, passed through via
  `CLIP_SCORING_PROVIDER` - the backend doesn't hardcode which LLM is used.
