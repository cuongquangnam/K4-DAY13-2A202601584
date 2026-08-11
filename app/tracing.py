from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except Exception:  # pragma: no cover
    pass


def _normalize_langfuse_env() -> None:
    """Align host aliases with the SDK (LANGFUSE_BASE_URL) and set trace env."""
    if not os.getenv("LANGFUSE_BASE_URL") and os.getenv("LANGFUSE_HOST"):
        os.environ["LANGFUSE_BASE_URL"] = os.environ["LANGFUSE_HOST"]
    if not os.getenv("LANGFUSE_TRACING_ENVIRONMENT"):
        os.environ["LANGFUSE_TRACING_ENVIRONMENT"] = os.getenv("APP_ENV", "dev")
    if not os.getenv("OTEL_SERVICE_NAME"):
        os.environ["OTEL_SERVICE_NAME"] = os.getenv("APP_NAME", "day13-observability-lab")


_normalize_langfuse_env()

try:
    from langfuse import get_client, observe

    LANGFUSE_SDK_AVAILABLE = True
except ImportError:  # pragma: no cover - chỉ dùng khi chưa cài requirements
    LANGFUSE_SDK_AVAILABLE = False

    def observe(*args: Any, **kwargs: Any):
        def decorator(func):
            return func

        if args and callable(args[0]) and not kwargs:
            return args[0]
        return decorator

    class _DummyObservation:
        def update(self, **kwargs: Any) -> None:
            return None

        def end(self) -> None:
            return None

        def __enter__(self) -> "_DummyObservation":
            return self

        def __exit__(self, *args: Any) -> None:
            return None

    class _DummyClient:
        def update_current_trace(self, **kwargs: Any) -> None:
            return None

        def update_current_generation(self, **kwargs: Any) -> None:
            return None

        def update_current_span(self, **kwargs: Any) -> None:
            return None

        def score_current_trace(self, **kwargs: Any) -> None:
            return None

        def get_current_trace_id(self) -> str | None:
            return None

        def flush(self) -> None:
            return None

        def shutdown(self) -> None:
            return None

        def start_as_current_observation(self, **kwargs: Any) -> _DummyObservation:
            return _DummyObservation()

        def get_prompt(self, *args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("Langfuse SDK unavailable")

    def get_client():
        return _DummyClient()


def get_langfuse_client():
    _normalize_langfuse_env()
    return get_client()


def tracing_enabled() -> bool:
    return LANGFUSE_SDK_AVAILABLE and bool(
        os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY")
    )


def flush_tracing() -> None:
    """Flush pending events (scripts / FastAPI shutdown)."""
    if not LANGFUSE_SDK_AVAILABLE:
        return
    try:
        get_langfuse_client().flush()
    except Exception:  # pragma: no cover - best-effort flush
        return


@contextmanager
def observation(
    *,
    name: str,
    as_type: str = "span",
    input: Any | None = None,
    metadata: dict[str, Any] | None = None,
    model: str | None = None,
    client: Any | None = None,
    **kwargs: Any,
) -> Iterator[Any]:
    """Nested observation helper; no-ops cleanly when the client lacks the API."""
    lf = client if client is not None else get_langfuse_client()
    start = getattr(lf, "start_as_current_observation", None)
    if not callable(start):
        yield None
        return

    params: dict[str, Any] = {"name": name, "as_type": as_type}
    if input is not None:
        params["input"] = input
    if metadata is not None:
        params["metadata"] = metadata
    if model is not None:
        params["model"] = model
    params.update(kwargs)

    with start(**params) as obs:
        yield obs
