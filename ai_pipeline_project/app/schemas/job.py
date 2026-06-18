import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class JobResponse(BaseModel):
    job_id: uuid.UUID
    status: str


class SummaryOverview(BaseModel):
    total_spend_inr: Decimal
    total_spend_usd: Decimal
    anomaly_count: int
    risk_level: str


class JobStatusResponse(BaseModel):
    job_id: uuid.UUID
    status: str
    summary: SummaryOverview | None = None


class LlmSummaryResponse(BaseModel):
    total_spend_inr: Decimal
    total_spend_usd: Decimal
    top_merchants: dict
    anomaly_count: int
    narrative: str
    risk_level: str


class JobResultResponse(BaseModel):
    cleaned_transactions: list[dict]
    flagged_anomalies: list[dict]
    category_breakdown: dict[str, Decimal]
    llm_summary: LlmSummaryResponse | None


class JobListItem(BaseModel):
    job_id: uuid.UUID
    status: str
    filename: str
    row_count_raw: int
    created_at: datetime


class JobListResponse(BaseModel):
    jobs: list[JobListItem]
