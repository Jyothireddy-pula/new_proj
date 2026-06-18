from decimal import Decimal

from app.services.pipeline_service import PipelineService


def test_clean_rows_handles_missing_txn_and_dedup():
    csv_payload = """txn_id,date,merchant,amount,currency,status,category,account_id,notes
,25-06-2024,Jio Recharge,4004.59,INR,PENDING,,ACC003,
,25-06-2024,Jio Recharge,4004.59,INR,PENDING,,ACC003,
TXN1,2024/02/05,Swiggy,$11325.79,inr,success,,ACC004,
"""
    service = PipelineService()

    rows, raw_count, clean_count = service.clean_rows(csv_payload)

    assert raw_count == 3
    assert clean_count == 2
    assert rows[0]["txn_id"] is None
    assert rows[0]["category"] == "Uncategorised"
    assert rows[1]["amount"] == Decimal("11325.79")
    assert rows[1]["currency"] == "INR"
    assert rows[1]["status"] == "SUCCESS"


def test_detect_anomalies_flags_outlier_and_cross_border():
    service = PipelineService()
    rows = [
        {"account_id": "ACC002", "amount": Decimal("100"), "currency": "INR", "merchant": "Swiggy", "category": "Food"},
        {"account_id": "ACC002", "amount": Decimal("110"), "currency": "INR", "merchant": "Swiggy", "category": "Food"},
        {"account_id": "ACC002", "amount": Decimal("1000"), "currency": "INR", "merchant": "IRCTC", "category": "Travel"},
        {"account_id": "ACC001", "amount": Decimal("500"), "currency": "USD", "merchant": "Zomato", "category": "Food"},
    ]

    flagged = service.detect_anomalies(rows)

    assert flagged[2]["is_anomaly"] is True
    assert "Outlier" in flagged[2]["anomaly_reason"]
    assert flagged[3]["is_anomaly"] is True
    assert "Cross-Border Mismatch" in flagged[3]["anomaly_reason"]


def test_classify_categories_marks_llm_failed_on_error():
    service = PipelineService()

    class _FailingLLM:
        @staticmethod
        def classify_uncategorised(_):
            raise RuntimeError("temporary outage")

    service.llm_service = _FailingLLM()
    rows = [
        {"merchant": "Amazon", "notes": None, "category": "Uncategorised", "llm_failed": False, "llm_category": None},
        {"merchant": "Swiggy", "notes": "ok", "category": "Food", "llm_failed": False, "llm_category": None},
    ]

    classified = service.classify_categories(rows)

    assert classified[0]["llm_failed"] is True
    assert classified[0]["category"] == "Uncategorised"
    assert classified[1]["llm_failed"] is False


def test_build_summary_payload_falls_back_when_llm_summary_fails():
    service = PipelineService()

    class _FailingSummaryLLM:
        @staticmethod
        def generate_summary(_):
            raise RuntimeError("quota exceeded")

    service.llm_service = _FailingSummaryLLM()
    rows = [
        {"merchant": "A", "amount": Decimal("100"), "currency": "INR", "is_anomaly": True},
        {"merchant": "B", "amount": Decimal("10"), "currency": "USD", "is_anomaly": False},
    ]

    summary = service.build_summary_payload(rows)

    assert summary["total_spend_inr"] == Decimal("100.00")
    assert summary["total_spend_usd"] == Decimal("10.00")
    assert summary["anomaly_count"] == 1
    assert summary["risk_level"].value == "MEDIUM"
    assert "AI-powered insights temporarily unavailable" in summary["narrative"]
