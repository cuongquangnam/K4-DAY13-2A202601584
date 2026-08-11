from __future__ import annotations

import os
import time
from dataclasses import dataclass

from . import metrics
from .mock_llm import FakeLLM
from .mock_rag import retrieve
from .pii import hash_user_id, scrub_text, summarize_text
from .prompt_management import resolve_prompt
from .tracing import get_langfuse_client, observation, observe, tracing_enabled


@dataclass
class AgentResult:
    answer: str
    latency_ms: int
    tokens_in: int
    tokens_out: int
    cost_usd: float
    quality_score: float
    langfuse_trace_id: str | None = None


class LabAgent:
    def __init__(self, model: str = "claude-sonnet-4-5") -> None:
        self.model = model
        self.llm = FakeLLM(model=model)

    @observe(name="chat-response", as_type="chain", capture_input=False, capture_output=False)
    def run(
        self,
        user_id: str,
        feature: str,
        session_id: str,
        message: str,
        correlation_id: str | None = None,
    ) -> AgentResult:
        started = time.perf_counter()
        langfuse_client = get_langfuse_client()
        user_hash = hash_user_id(user_id)
        message_preview = summarize_text(message)

        # Root input: user message only (not full function args / secrets).
        if hasattr(langfuse_client, "update_current_span"):
            langfuse_client.update_current_span(
                input={"message": message_preview, "feature": feature},
            )

        docs = self._retrieve_context(langfuse_client, message, message_preview)

        prompt = resolve_prompt(
            langfuse_client,
            feature=feature,
            docs=docs,
            message=message,
            enabled=tracing_enabled(),
        )

        response = self._generate_response(
            langfuse_client,
            prompt_text=prompt.text,
            managed_prompt=prompt.managed_prompt,
            message_preview=message_preview,
            prompt_meta={
                "prompt_name": prompt.name,
                "prompt_label": prompt.label,
                "prompt_version": prompt.version,
                "prompt_source": prompt.source,
                "prompt_fetch_error": prompt.fetch_error,
                "doc_count": len(docs),
                "query_preview": message_preview,
            },
        )

        quality_score = self._heuristic_quality(message, response.text, docs)
        latency_ms = int((time.perf_counter() - started) * 1000)
        cost_usd = self._estimate_cost(response.usage.input_tokens, response.usage.output_tokens)
        answer_preview = summarize_text(response.text)

        trace_metadata = {
            "prompt_name": prompt.name,
            "prompt_label": prompt.label,
            "prompt_version": prompt.version,
            "prompt_source": prompt.source,
        }
        request_context = {
            "feature": feature,
            "model": self.model,
            "env": os.getenv("APP_ENV", "dev"),
            "service": os.getenv("APP_NAME", "day13-observability-lab"),
        }
        if correlation_id:
            request_context["correlation_id"] = correlation_id

        langfuse_client.update_current_trace(
            name="chat-response",
            user_id=user_hash,
            session_id=session_id,
            tags=["lab", feature, self.model],
            metadata=trace_metadata,
            input={
                "message": message_preview,
                "feature": feature,
                **({"correlation_id": correlation_id} if correlation_id else {}),
            },
            output={"answer": answer_preview},
        )
        if hasattr(langfuse_client, "update_current_span"):
            langfuse_client.update_current_span(
                output={"answer": answer_preview, "quality_score": quality_score},
                metadata={**trace_metadata, **request_context},
            )

        # Flat-path generation metadata for unit tests / non-nested clients.
        if not tracing_enabled() or not hasattr(langfuse_client, "start_as_current_observation"):
            langfuse_client.update_current_generation(
                model=self.model,
                metadata={
                    "doc_count": len(docs),
                    "query_preview": message_preview,
                    "prompt_name": prompt.name,
                    "prompt_label": prompt.label,
                    "prompt_version": prompt.version,
                    "prompt_source": prompt.source,
                    "prompt_fetch_error": prompt.fetch_error,
                },
                usage_details={
                    "input": response.usage.input_tokens,
                    "output": response.usage.output_tokens,
                },
                cost_details={"total": cost_usd},
                prompt=prompt.managed_prompt,
                input=[{"role": "user", "content": message_preview}],
                output=answer_preview,
            )

        score_fn = getattr(langfuse_client, "score_current_trace", None)
        if callable(score_fn):
            try:
                score_fn(name="quality_proxy", value=quality_score)
            except Exception:  # pragma: no cover
                pass

        metrics.record_request(
            latency_ms=latency_ms,
            cost_usd=cost_usd,
            tokens_in=response.usage.input_tokens,
            tokens_out=response.usage.output_tokens,
            quality_score=quality_score,
        )

        trace_id = None
        get_trace_id = getattr(langfuse_client, "get_current_trace_id", None)
        if callable(get_trace_id):
            try:
                trace_id = get_trace_id()
            except Exception:  # pragma: no cover
                trace_id = None

        return AgentResult(
            answer=response.text,
            latency_ms=latency_ms,
            tokens_in=response.usage.input_tokens,
            tokens_out=response.usage.output_tokens,
            cost_usd=cost_usd,
            quality_score=quality_score,
            langfuse_trace_id=trace_id,
        )

    def _retrieve_context(self, client, message: str, message_preview: str) -> list[str]:
        with observation(
            name="retrieve-context",
            as_type="retriever",
            input={"query": message_preview},
            metadata={"source": "mock-rag-corpus"},
            client=client,
        ) as ret:
            docs = retrieve(message)
            if ret is not None:
                ret.update(
                    output={
                        "documents": [scrub_text(doc) for doc in docs],
                        "doc_count": len(docs),
                    }
                )
            return docs

    def _generate_response(
        self,
        client,
        *,
        prompt_text: str,
        managed_prompt: object | None,
        message_preview: str,
        prompt_meta: dict,
    ):
        obs_kwargs: dict = {
            "name": "generate-response",
            "as_type": "generation",
            "model": self.model,
            "input": [{"role": "user", "content": message_preview}],
            "metadata": prompt_meta,
            "client": client,
        }
        if managed_prompt is not None:
            obs_kwargs["prompt"] = managed_prompt
        with observation(**obs_kwargs) as gen:
            response = self.llm.generate(prompt_text)
            cost_usd = self._estimate_cost(
                response.usage.input_tokens, response.usage.output_tokens
            )
            answer_preview = summarize_text(response.text)
            generation_kwargs = {
                "model": self.model,
                "output": answer_preview,
                # Langfuse standard usage keys for token/cost dashboards.
                "usage_details": {
                    "input": response.usage.input_tokens,
                    "output": response.usage.output_tokens,
                },
                "cost_details": {
                    "input": self._estimate_cost(response.usage.input_tokens, 0),
                    "output": self._estimate_cost(0, response.usage.output_tokens),
                    "total": cost_usd,
                },
                "metadata": prompt_meta,
            }
            if managed_prompt is not None:
                generation_kwargs["prompt"] = managed_prompt
            if gen is not None:
                gen.update(**generation_kwargs)
            return response

    def _estimate_cost(self, tokens_in: int, tokens_out: int) -> float:
        input_cost = (tokens_in / 1_000_000) * 3
        output_cost = (tokens_out / 1_000_000) * 15
        return round(input_cost + output_cost, 6)

    def _heuristic_quality(self, question: str, answer: str, docs: list[str]) -> float:
        score = 0.5
        if docs:
            score += 0.2
        if len(answer) > 40:
            score += 0.1
        if question.lower().split()[0:1] and any(
            token in answer.lower() for token in question.lower().split()[:3]
        ):
            score += 0.1
        if "[REDACTED" in answer:
            score -= 0.2
        return round(max(0.0, min(1.0, score)), 2)
