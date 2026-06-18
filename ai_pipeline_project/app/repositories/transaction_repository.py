import uuid
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import func, select

from app.models.summary import JobSummary, RiskLevel
from app.models.transaction import Transaction
from app.repositories.base import BaseRepository


class TransactionRepository(BaseRepository):
    async def bulk_create(self, transactions: list[dict]) -> list[Transaction]:
        rows = [Transaction(**item) for item in transactions]
        self.session.add_all(rows)
        await self.session.flush()
        return rows

    async def list_by_job(self, job_id: uuid.UUID) -> list[Transaction]:
        result = await self.session.execute(select(Transaction).where(Transaction.job_id == job_id).order_by(Transaction.date.asc()))
        return list(result.scalars().all())

    async def list_anomalies(self, job_id: uuid.UUID) -> list[Transaction]:
        result = await self.session.execute(
            select(Transaction).where(Transaction.job_id == job_id, Transaction.is_anomaly.is_(True)).order_by(Transaction.date.asc())
        )
        return list(result.scalars().all())

    async def category_breakdown(self, job_id: uuid.UUID) -> dict[str, Decimal]:
        result = await self.session.execute(
            select(Transaction.category, func.sum(Transaction.amount)).where(Transaction.job_id == job_id).group_by(Transaction.category)
        )
        breakdown: dict[str, Decimal] = defaultdict(Decimal)
        for category, total in result.all():
            breakdown[category] = Decimal(total)
        return dict(breakdown)

    async def upsert_summary(self, payload: dict) -> JobSummary:
        result = await self.session.execute(select(JobSummary).where(JobSummary.job_id == payload["job_id"]))
        summary = result.scalar_one_or_none()
        if summary:
            for key, value in payload.items():
                setattr(summary, key, value)
        else:
            summary = JobSummary(**payload)
            self.session.add(summary)
        await self.session.flush()
        return summary

    async def get_summary(self, job_id: uuid.UUID) -> JobSummary | None:
        result = await self.session.execute(select(JobSummary).where(JobSummary.job_id == job_id))
        return result.scalar_one_or_none()


__all__ = ["TransactionRepository", "RiskLevel"]
