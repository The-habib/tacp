"""Unit tests for RequestTracer."""

from tacp.core.tracer import RequestTracer, NoopTracer, get_current_tracer, set_current_tracer, _NOOP_SPAN


def test_request_tracer_lifecycle():
    tracer = RequestTracer(trace_id="tr_123", request_id="req_456", enabled=True)
    with tracer.span("phase_1", detail="init") as s:
        assert s.name == "phase_1"
        assert s.metadata == {"detail": "init"}
    
    with tracer.span("phase_2"):
        pass

    tracer.finish()
    assert tracer.total_duration_ns > 0
    assert len(tracer.spans) == 2
    summary = tracer.summary()
    assert summary["trace_id"] == "tr_123"
    assert summary["request_id"] == "req_456"
    assert len(summary["spans"]) == 2
    assert summary["spans"][0]["name"] == "phase_1"
    assert summary["spans"][0]["metadata"] == {"detail": "init"}
    breakdown = tracer.get_breakdown()
    assert "phase_1" in breakdown
    assert "phase_2" in breakdown


def test_noop_tracer():
    tracer = NoopTracer()
    assert not tracer.enabled
    with tracer.span("phase_x") as s:
        assert s is _NOOP_SPAN
    assert tracer.total_duration_ns == 0
    assert tracer.get_breakdown() == {}


def test_context_var_tracer():
    tracer = RequestTracer("t1", "r1", enabled=True)
    token = set_current_tracer(tracer)
    try:
        current = get_current_tracer()
        assert current is tracer
        with current.span("auth"):
            pass
        assert len(tracer.spans) == 1
    finally:
        set_current_tracer(None)
    assert isinstance(get_current_tracer(), NoopTracer)
