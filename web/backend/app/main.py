from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import internal, jobs, uploads
from app.jobs_repo import init_db

app = FastAPI(title="KatGai Reel API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to the deployed frontend origin before going live
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(uploads.router)
app.include_router(jobs.router)
app.include_router(internal.router)


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/health")
def health():
    return {"status": "ok"}
