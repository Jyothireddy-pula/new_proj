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
