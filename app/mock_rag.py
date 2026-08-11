from __future__ import annotations

import time

from .incidents import STATE
from .logging_config import get_logger

log = get_logger()

CORPUS = {
    "refund": ["Refunds are available within 7 days with proof of purchase."],
    "monitoring": ["Metrics detect incidents, traces localize them, logs explain root cause."],
    "policy": ["Do not expose PII in logs. Use sanitized summaries only."],
}


def retrieve(message: str) -> list[str]:
    if STATE["tool_fail"]:
        raise RuntimeError("Vector store timeout")
    if STATE["rag_slow"]:
        log.warning(
            "rag_retrieval_slow",
            service="rag",
            tool_name="mock_rag.retrieve",
            latency_ms=2500,
            payload={"incident": "rag_slow"},
        )
        time.sleep(2.5)
    lowered = message.lower()
    for key, docs in CORPUS.items():
        if key in lowered:
            return docs
    return ["No domain document matched. Use general fallback answer."]
