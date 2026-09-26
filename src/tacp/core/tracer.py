"""Deterministic request lifecycle tracer for TACP.

Provides nanosecond-precision tracing across all 11 phases of the TACP request lifecycle:
1. transport_receive
2. authentication
3. session
4. policy
5. capability_resolution
6. provider_resolution
7. cache
8. execution
9. serialization
10. audit
11. transport_write

Designed for zero allocation when disabled and sub-microsecond overhead when enabled.
"""

from __future__ import annotations

import contextvars
import time
from typing import Any, Dict, List, Optional


class TraceSpan:
    """A single timed execution span."""

    __slots__ = ("name", "start_ns", "end_ns", "duration_ns", "metadata", "_tracer")

    def __init__(
        self,
        name: str,
        tracer: Optional[RequestTracer] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.name = name
        self.start_ns = 0
        self.end_ns = 0
        self.duration_ns = 0
        self.metadata: Dict[str, Any] = metadata or {}
        self._tracer = tracer

    def __enter__(self) -> TraceSpan:
        self.start_ns = time.perf_counter_ns()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        self.end_ns = time.perf_counter_ns()
        self.duration_ns = self.end_ns - self.start_ns
        if self._tracer is not None:
            self._tracer._record_span(self)
        return False

    def finish(self, **meta: Any) -> None:
        if self.end_ns == 0:
            self.end_ns = time.perf_counter_ns()
            self.duration_ns = self.end_ns - self.start_ns
        if meta:
            self.metadata.update(meta)
        if self._tracer is not None:
            self._tracer._record_span(self)

    @property
    def duration_ms(self) -> float:
        return self.duration_ns / 1_000_000.0


class NoopSpan:
    """Zero-allocation no-op span context manager."""

    __slots__ = ()

    def __enter__(self) -> NoopSpan:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        return False

    def finish(self, **meta: Any) -> None:
        pass

    @property
    def duration_ms(self) -> float:
        return 0.0

    @property
    def duration_ns(self) -> int:
        return 0


_NOOP_SPAN = NoopSpan()


class RequestTracer:
    """Deterministic request lifecycle tracer."""

    __slots__ = (
        "trace_id",
        "request_id",
        "enabled",
        "start_ns",
        "end_ns",
        "spans",
        "_active_spans",
    )

    def __init__(
        self,
        trace_id: Optional[str] = None,
        request_id: Optional[str] = None,
        enabled: bool = True,
    ) -> None:
        self.trace_id = trace_id or ""
        self.request_id = request_id or ""
        self.enabled = enabled
        self.start_ns = time.perf_counter_ns() if enabled else 0
        self.end_ns = 0
        self.spans: List[TraceSpan] = []
        self._active_spans: Dict[str, TraceSpan] = {}

    def _record_span(self, span: TraceSpan) -> None:
        self.spans.append(span)

    def span(self, name: str, **meta: Any) -> Any:
        if not self.enabled:
            return _NOOP_SPAN
        span_obj = TraceSpan(name=name, tracer=self, metadata=meta)
        return span_obj

    def start_span(self, name: str, **meta: Any) -> Any:
        if not self.enabled:
            return _NOOP_SPAN
        span_obj = TraceSpan(name=name, tracer=self, metadata=meta)
        span_obj.start_ns = time.perf_counter_ns()
        self._active_spans[name] = span_obj
        return span_obj

    def end_span(self, name: str, **meta: Any) -> None:
        if not self.enabled:
            return
        span_obj = self._active_spans.pop(name, None)
        if span_obj is not None:
            span_obj.finish(**meta)

    def finish(self) -> None:
        if not self.enabled:
            return
        self.end_ns = time.perf_counter_ns()
        for span_obj in list(self._active_spans.values()):
            if span_obj.end_ns == 0:
                span_obj.finish()
        self._active_spans.clear()

    @property
    def total_duration_ns(self) -> int:
        if self.end_ns == 0:
            return time.perf_counter_ns() - self.start_ns
        return self.end_ns - self.start_ns

    @property
    def total_duration_ms(self) -> float:
        return self.total_duration_ns / 1_000_000.0

    def get_breakdown(self) -> Dict[str, float]:
        """Return mapping of span_name -> duration_ms."""
        return {s.name: s.duration_ms for s in self.spans}

    def summary(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "request_id": self.request_id,
            "total_ms": round(self.total_duration_ms, 4),
            "spans": [
                {
                    "name": s.name,
                    "duration_ms": round(s.duration_ms, 4),
                    "duration_ns": s.duration_ns,
                    "metadata": s.metadata,
                }
                for s in self.spans
            ],
        }


class NoopTracer(RequestTracer):
    """Zero-allocation no-op tracer."""

    def __init__(self) -> None:
        super().__init__(enabled=False)

    @property
    def total_duration_ns(self) -> int:
        return 0

    @property
    def total_duration_ms(self) -> float:
        return 0.0

    def span(self, name: str, **meta: Any) -> Any:
        return _NOOP_SPAN

    def start_span(self, name: str, **meta: Any) -> Any:
        return _NOOP_SPAN

    def end_span(self, name: str, **meta: Any) -> None:
        pass

    def finish(self) -> None:
        pass


_NOOP_TRACER = NoopTracer()

_active_tracer: contextvars.ContextVar[Optional[RequestTracer]] = contextvars.ContextVar(
    "active_tracer", default=None
)


def get_current_tracer() -> RequestTracer:
    t = _active_tracer.get()
    return t if t is not None else _NOOP_TRACER


def set_current_tracer(tracer: Optional[RequestTracer]) -> contextvars.Token:
    return _active_tracer.set(tracer)
