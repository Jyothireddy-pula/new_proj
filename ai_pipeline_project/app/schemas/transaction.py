import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class TransactionResponse(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    txn_id: str | None
    date: date
    merchant: str
    amount: Decimal
    currency: str
    status: str
    category: str
    account_id: str
    notes: str | None
    is_anomaly: bool
    anomaly_reason: str | None
    llm_category: str | None
    llm_failed: bool
