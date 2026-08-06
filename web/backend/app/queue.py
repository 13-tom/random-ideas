"""Push-based job queue: enqueuing a job means scheduling a call to
POST /internal/jobs/{id}/run, not starting work inline in the request that
created the job. Two implementations behind the same interface:

- LocalQueue: fires the internal endpoint from an asyncio background task,
  in-process. Fine for local dev and a single-instance deployment; not a
  real queue (no retry, no persistence across a crash).
- CloudTasksQueue: enqueues a real Cloud Tasks push task pointed at the
  same internal endpoint - this is what gives genuine scale-to-zero
  behavior in production (see project planning notes: nothing needs to
  stay alive polling a table). Selected via settings.queue_backend.

pipeline_runner.py and the API routes only ever call get_queue().enqueue() -
neither needs to know which implementation is active.
"""
import asyncio
from typing import Protocol

import httpx

from app.config import settings


class JobQueue(Protocol):
    def enqueue(self, job_id: str) -> None: ...


class LocalQueue:
    def enqueue(self, job_id: str) -> None:
        asyncio.create_task(self._fire(job_id))

    async def _fire(self, job_id: str):
        url = f"{settings.internal_base_url.rstrip('/')}/internal/jobs/{job_id}/run"
        async with httpx.AsyncClient(timeout=None) as client:
            try:
                await client.post(url)
            except httpx.HTTPError as e:
                print(f"[queue] failed to trigger job {job_id}: {e}")


class CloudTasksQueue:
    """Enqueues a Cloud Tasks push task. Requires gcp_project_id,
    gcp_location, and cloud_tasks_queue_name to be configured - raises
    clearly at construction time if they aren't, rather than failing
    confusingly on the first enqueue() call."""

    def __init__(self):
        if not (settings.gcp_project_id and settings.gcp_location and settings.cloud_tasks_queue_name):
            raise RuntimeError(
                "queue_backend=cloud_tasks requires gcp_project_id, gcp_location, and "
                "cloud_tasks_queue_name to be set"
            )
        from google.cloud import tasks_v2
        self._client = tasks_v2.CloudTasksClient()
        self._queue_path = self._client.queue_path(settings.gcp_project_id, settings.gcp_location, settings.cloud_tasks_queue_name)

    def enqueue(self, job_id: str) -> None:
        from google.cloud import tasks_v2
        url = f"{settings.internal_base_url.rstrip('/')}/internal/jobs/{job_id}/run"
        task = tasks_v2.Task(http_request=tasks_v2.HttpRequest(http_method=tasks_v2.HttpMethod.POST, url=url))
        self._client.create_task(parent=self._queue_path, task=task)


_queue_instance: JobQueue | None = None


def get_queue() -> JobQueue:
    global _queue_instance
    if _queue_instance is None:
        _queue_instance = CloudTasksQueue() if settings.queue_backend == "cloud_tasks" else LocalQueue()
    return _queue_instance
