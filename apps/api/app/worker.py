import asyncio
import os
import socket
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select

from app.core.config import get_settings
from app.core.enums import JobStatus
from app.db import SessionLocal, init_db
from app.models import ProcessingJob
from app.pipeline.runner import process_job

settings = get_settings()
worker_id = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


async def claim_job() -> uuid.UUID | None:
    now = datetime.now(UTC)
    async with SessionLocal() as session, session.begin():
        job = await session.scalar(
            select(ProcessingJob)
            .where(
                or_(
                    ProcessingJob.status == JobStatus.QUEUED,
                    (ProcessingJob.status == JobStatus.RUNNING)
                    & (ProcessingJob.leased_until < now),
                )
            )
            .order_by(ProcessingJob.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if job is None:
            return None
        job.status = JobStatus.RUNNING
        job.worker_id = worker_id
        job.leased_until = now + timedelta(seconds=settings.worker_lease_seconds)
        job.started_at = job.started_at or now
        job.attempt_count += 1
        return job.id


async def run() -> None:
    await init_db()
    while True:
        job_id = await claim_job()
        if job_id is None:
            await asyncio.sleep(settings.worker_poll_seconds)
            continue
        await process_job(job_id)


if __name__ == "__main__":
    asyncio.run(run())
