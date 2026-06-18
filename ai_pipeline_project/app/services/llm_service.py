import json
import logging
import time
from typing import Any

import google.generativeai as genai

from app.config import get_settings

logger = logging.getLogger(__name__)

ALLOWED_CATEGORIES = [
    "Food",
    "Shopping",
    "Travel",
    "Transport",
    "Utilities",
    "Cash Withdrawal",
    "Entertainment",
    "Other",
]


class LLMService:
    def __init__(self) -> None:
        self.settings = get_settings()
        if self.settings.GEMINI_API_KEY:
            genai.configure(api_key=self.settings.GEMINI_API_KEY)

    def _retry_call(self, fn) -> Any:
        last_error: Exception | None = None
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                return fn()
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                sleep_for = 2**attempt
                logger.warning("[LLM Retry] attempt=%s wait=%s error=%s", attempt + 1, sleep_for, str(exc))
                time.sleep(sleep_for)
        if last_error:
            raise RuntimeError(
                f"LLM request failed after {max_attempts} retry attempts: {type(last_error).__name__}: {last_error}"
            ) from last_error
        raise RuntimeError(f"LLM request failed after {max_attempts} retry attempts")

    def classify_uncategorised(self, rows: list[dict]) -> dict[int, str]:
        if not rows:
            return {}

        prompt = (
            "Classify each transaction row into one of these categories only: "
            f"{', '.join(ALLOWED_CATEGORIES)}. "
            "Return strict JSON object mapping row_index to category. "
            f"rows={json.dumps(rows)}"
        )

        def _call() -> dict[int, str]:
            if not self.settings.GEMINI_API_KEY:
                raise RuntimeError("Missing GEMINI_API_KEY")
            model = genai.GenerativeModel("gemini-1.5-flash")
            response = model.generate_content(prompt)
            parsed = json.loads(response.text)
            return {int(k): v for k, v in parsed.items()}

        return self._retry_call(_call)

    def generate_summary(self, payload: dict) -> dict:
        prompt = (
            "Return strict JSON with keys: total_spend_by_currency, top_merchants, anomaly_count, "
            "narrative (2-3 sentences), risk_level (low/medium/high). "
            f"Input data: {json.dumps(payload)}"
        )

        def _call() -> dict:
            if not self.settings.GEMINI_API_KEY:
                raise RuntimeError("Missing GEMINI_API_KEY")
            model = genai.GenerativeModel("gemini-1.5-flash")
            response = model.generate_content(prompt)
            return json.loads(response.text)

        return self._retry_call(_call)
