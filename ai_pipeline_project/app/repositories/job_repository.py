import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.models.job import Job, JobStatus
from app.repositories.base import BaseRepository


class JobRepository(BaseRepository):
    async def create(self, filename: str) -> Job:
        job = Job(filename=filename, status=JobStatus.PENDING)
        self.session.add(job)
        await self.session.flush()
        return job

    async def get(self, job_id: uuid.UUID) -> Job | None:
        result = await self.session.execute(select(Job).where(Job.id == job_id))
        return result.scalar_one_or_none()

    async def list(self, status: str | None = None) -> list[Job]:
        stmt = select(Job).order_by(Job.created_at.desc())
        if status:
            stmt = stmt.where(Job.status == JobStatus(status.upper()))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_status(self, job: Job, status: JobStatus, error_message: str | None = None) -> Job:
        job.status = status
        job.error_message = error_message
        if status in (JobStatus.COMPLETED, JobStatus.FAILED):
            job.completed_at = datetime.now(timezone.utc)
        self.session.add(job)
        await self.session.flush()
        return job
