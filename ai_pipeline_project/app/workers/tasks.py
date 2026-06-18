import asyncio
import logging
import traceback
import uuid

from celery import Celery

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.models.job import JobStatus
from app.repositories.job_repository import JobRepository
from app.repositories.transaction_repository import TransactionRepository
from app.services.pipeline_service import PipelineService

logger = logging.getLogger(__name__)

settings = get_settings()
celery_app = Celery("transaction_worker", broker=settings.REDIS_URL, backend=settings.REDIS_URL)


@celery_app.task(name="app.workers.tasks.process_job", bind=True)
def process_job(self, job_id: str, csv_content: str) -> None:
    asyncio.run(_process_job_async(job_id, csv_content))


async def _process_job_async(job_id: str, csv_content: str) -> None:
    job_uuid = uuid.UUID(job_id)
    session = AsyncSessionLocal()
    try:
        logger.info("[Task Dequeued] job_id=%s", job_id)
        job_repo = JobRepository(session)
        txn_repo = TransactionRepository(session)
        pipeline = PipelineService()

        job = await job_repo.get(job_uuid)
        if not job:
            return

        await job_repo.update_status(job, JobStatus.PROCESSING)
        await session.commit()

        rows, raw_count, clean_count, summary_payload = pipeline.process_csv(job_uuid, csv_content)

        async with session.begin():
            job.row_count_raw = raw_count
            job.row_count_clean = clean_count
            await txn_repo.bulk_create(rows)
            summary_payload["job_id"] = job_uuid
            await txn_repo.upsert_summary(summary_payload)
            await job_repo.update_status(job, JobStatus.COMPLETED)

        logger.info("[Job Finalized Successfully] job_id=%s", job_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("[Worker Failure] job_id=%s", job_id)
        try:
            job_repo = JobRepository(session)
            job = await job_repo.get(job_uuid)
            if job:
                await job_repo.update_status(job, JobStatus.FAILED, error_message=traceback.format_exc())
                await session.commit()
        except Exception:  # noqa: BLE001
            logger.exception("[Worker Failure During Recovery] job_id=%s error=%s", job_id, str(exc))
    finally:
        await session.close()
