import csv
import io
import logging
import uuid
from collections import Counter
from datetime import datetime
from decimal import Decimal
from statistics import median

from dateutil import parser

from app.models.summary import RiskLevel
from app.services.llm_service import LLMService

logger = logging.getLogger(__name__)

DOMESTIC_ONLY_MERCHANTS = {"swiggy", "ola", "irctc", "zomato", "makemytrip"}


class PipelineService:
    def __init__(self) -> None:
        self.llm_service = LLMService()

    @staticmethod
    def _parse_date(value: str):
        return parser.parse(value, dayfirst=True).date()

    @staticmethod
    def _parse_amount(value: str) -> Decimal:
        cleaned = (value or "0").strip().replace("$", "")
        return Decimal(cleaned)

    def clean_rows(self, csv_content: str) -> tuple[list[dict], int, int]:
        reader = csv.DictReader(io.StringIO(csv_content))
        rows = list(reader)
        raw_count = len(rows)

        deduped = []
        seen = set()
        for row in rows:
            key = tuple((k, (v or "").strip()) for k, v in row.items())
            if key in seen:
                continue
            seen.add(key)

            category = (row.get("category") or "").strip() or "Uncategorised"
            cleaned = {
                "txn_id": (row.get("txn_id") or "").strip() or None,
                "date": self._parse_date((row.get("date") or "").strip()),
                "merchant": (row.get("merchant") or "").strip(),
                "amount": self._parse_amount(row.get("amount") or "0"),
                "currency": (row.get("currency") or "").strip().upper(),
                "status": (row.get("status") or "").strip().upper(),
                "category": category,
                "account_id": (row.get("account_id") or "").strip(),
                "notes": (row.get("notes") or "").strip() or None,
            }
            deduped.append(cleaned)

        logger.info("[Cleaning Step Complete] raw=%s clean=%s", raw_count, len(deduped))
        return deduped, raw_count, len(deduped)

    def detect_anomalies(self, rows: list[dict]) -> list[dict]:
        by_account: dict[str, list[Decimal]] = {}
        for row in rows:
            by_account.setdefault(row["account_id"], []).append(row["amount"])

        account_medians = {acc: Decimal(str(median(vals))) for acc, vals in by_account.items()}
        anomaly_count = 0

        for row in rows:
            reasons = []
            if row["amount"] > account_medians[row["account_id"]] * Decimal("3"):
                reasons.append("Outlier: Amount exceeds 3x the account median")
            if row["currency"] == "USD" and row["merchant"].strip().lower() in DOMESTIC_ONLY_MERCHANTS:
                reasons.append("Cross-Border Mismatch: USD currency utilized at a strict domestic merchant entity")

            row["is_anomaly"] = bool(reasons)
            row["anomaly_reason"] = " | ".join(reasons) if reasons else None
            row["llm_category"] = None
            row["llm_failed"] = False
            if reasons:
                anomaly_count += 1

        logger.info("[Anomalies Found: %s]", anomaly_count)
        return rows

    def classify_categories(self, rows: list[dict]) -> list[dict]:
        batch = [{"row_index": idx, "merchant": row["merchant"], "notes": row.get("notes")} for idx, row in enumerate(rows) if row["category"] == "Uncategorised"]
        if not batch:
            return rows

        try:
            result = self.llm_service.classify_uncategorised(batch)
            for idx, category in result.items():
                if 0 <= idx < len(rows):
                    rows[idx]["llm_category"] = category
                    rows[idx]["category"] = category
        except Exception as exc:  # noqa: BLE001
            logger.warning("[LLM Classification Failed] %s", str(exc))
            for item in batch:
                rows[item["row_index"]]["llm_failed"] = True

        return rows

    def build_summary_payload(self, rows: list[dict]) -> dict:
        total_spend_inr = sum((row["amount"] for row in rows if row["currency"] == "INR"), Decimal("0"))
        total_spend_usd = sum((row["amount"] for row in rows if row["currency"] == "USD"), Decimal("0"))
        top_merchants = [name for name, _ in Counter([r["merchant"] for r in rows]).most_common(3)]
        anomaly_count = sum(1 for row in rows if row["is_anomaly"])

        payload = {
            "total_spend_by_currency": {"INR": float(total_spend_inr), "USD": float(total_spend_usd)},
            "top_merchants": top_merchants,
            "anomaly_count": anomaly_count,
        }

        try:
            llm_summary = self.llm_service.generate_summary(payload)
            narrative = llm_summary.get("narrative", "Spending was reviewed with mixed patterns and anomaly checks completed.")
            risk = (llm_summary.get("risk_level") or "medium").upper()
        except Exception as exc:  # noqa: BLE001
            logger.warning("[LLM Summary Failed] %s", str(exc))
            narrative = "Spending data was processed successfully. Some AI enrichments were unavailable, but anomaly checks completed. Review flagged transactions for manual validation."
            risk = "MEDIUM" if anomaly_count else "LOW"

        return {
            "total_spend_inr": total_spend_inr.quantize(Decimal("0.01")),
            "total_spend_usd": total_spend_usd.quantize(Decimal("0.01")),
            "top_merchants": {"items": top_merchants},
            "anomaly_count": anomaly_count,
            "narrative": narrative,
            "risk_level": RiskLevel[risk if risk in RiskLevel.__members__ else "MEDIUM"],
        }

    def process_csv(self, job_id: uuid.UUID, csv_content: str) -> tuple[list[dict], int, int, dict]:
        rows, raw_count, clean_count = self.clean_rows(csv_content)
        rows = self.detect_anomalies(rows)
        rows = self.classify_categories(rows)
        for row in rows:
            row["job_id"] = job_id
        summary = self.build_summary_payload(rows)
        return rows, raw_count, clean_count, summary
