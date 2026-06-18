import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, init_db
from app.models.job import JobStatus
from app.repositories.job_repository import JobRepository
from app.repositories.transaction_repository import TransactionRepository
from app.schemas.job import JobListItem, JobListResponse, JobResponse, JobResultResponse, JobStatusResponse, LlmSummaryResponse, SummaryOverview
from app.workers.tasks import process_job

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    yield


app = FastAPI(lifespan=lifespan, title="Transaction Pipeline")


@app.get("/", response_class=HTMLResponse)
async def serve_dashboard() -> str:
    template_path = Path(__file__).resolve().parent.parent / "templates" / "dashboard.html"
    if not template_path.exists():
        raise HTTPException(status_code=404, detail="Dashboard template file not found.")
    with open(template_path, "r", encoding="utf-8") as file:
        return file.read()


@app.post("/jobs/upload", response_model=JobResponse, status_code=202)
async def upload_job(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)) -> JobResponse:
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV uploads are supported")

    logger.info("[API Upload Triggered] filename=%s", file.filename)
    content = bytearray()
    while chunk := await file.read(64 * 1024):
        content.extend(chunk)

    job_repo = JobRepository(db)
    job = await job_repo.create(filename=file.filename)
    await db.commit()

    process_job.delay(str(job.id), content.decode("utf-8", errors="ignore"))
    return JobResponse(job_id=job.id, status=job.status.value.lower())


@app.get("/jobs/{job_id}/status", response_model=JobStatusResponse)
async def job_status(job_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> JobStatusResponse:
    job_repo = JobRepository(db)
    txn_repo = TransactionRepository(db)

    job = await job_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    summary = None
    if job.status == JobStatus.COMPLETED:
        db_summary = await txn_repo.get_summary(job_id)
        if db_summary:
            summary = SummaryOverview(
                total_spend_inr=db_summary.total_spend_inr,
                total_spend_usd=db_summary.total_spend_usd,
                anomaly_count=db_summary.anomaly_count,
                risk_level=db_summary.risk_level.value.lower(),
            )

    return JobStatusResponse(job_id=job.id, status=job.status.value.lower(), summary=summary)


@app.get("/jobs/{job_id}/results", response_model=JobResultResponse)
async def job_results(job_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> JobResultResponse:
    job_repo = JobRepository(db)
    txn_repo = TransactionRepository(db)

    job = await job_repo.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != JobStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="Job is not completed")

    rows = await txn_repo.list_by_job(job_id)
    anomalies = await txn_repo.list_anomalies(job_id)
    breakdown = await txn_repo.category_breakdown(job_id)
    summary = await txn_repo.get_summary(job_id)

    llm_summary = None
    if summary:
        llm_summary = LlmSummaryResponse(
            total_spend_inr=summary.total_spend_inr,
            total_spend_usd=summary.total_spend_usd,
            top_merchants=summary.top_merchants,
            anomaly_count=summary.anomaly_count,
            narrative=summary.narrative,
            risk_level=summary.risk_level.value.lower(),
        )

    return JobResultResponse(
        cleaned_transactions=[
            {
                "id": row.id,
                "job_id": row.job_id,
                "txn_id": row.txn_id,
                "date": row.date,
                "merchant": row.merchant,
                "amount": row.amount,
                "currency": row.currency,
                "status": row.status,
                "category": row.category,
                "account_id": row.account_id,
                "notes": row.notes,
                "is_anomaly": row.is_anomaly,
                "anomaly_reason": row.anomaly_reason,
                "llm_category": row.llm_category,
                "llm_failed": row.llm_failed,
            }
            for row in rows
        ],
        flagged_anomalies=[
            {
                "id": row.id,
                "txn_id": row.txn_id,
                "merchant": row.merchant,
                "amount": row.amount,
                "anomaly_reason": row.anomaly_reason,
            }
            for row in anomalies
        ],
        category_breakdown=breakdown,
        llm_summary=llm_summary,
    )


@app.get("/jobs", response_model=JobListResponse)
async def list_jobs(status: str | None = Query(default=None), db: AsyncSession = Depends(get_db)) -> JobListResponse:
    job_repo = JobRepository(db)
    try:
        jobs = await job_repo.list(status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid status filter") from exc

    return JobListResponse(
        jobs=[
            JobListItem(
                job_id=job.id,
                status=job.status.value.lower(),
                filename=job.filename,
                row_count_raw=job.row_count_raw,
                created_at=job.created_at,
            )
            for job in jobs
        ]
    )
