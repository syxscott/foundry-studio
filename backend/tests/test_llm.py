"""Tests for the LLM provider layer, planner integration, and the agent API.

Covers:
- OpenAI-compatible provider streaming against a real local SSE mock server.
- Normalized error (missing credential) handling.
- Planner LLM path + heuristic fallback (no network, via a fake provider).
- /chat SSE, /run, /capabilities, /health endpoints.
"""

from __future__ import annotations

import asyncio
import json as _json
import threading
import http.server

import pytest

from foundry_studio.agent.planner import Planner
from foundry_studio.llm.base import (
    BackoffConfig,
    BaseLLMProvider,
    FinishReason,
    LLMError,
    StreamChunk,
    TokenUsage,
    errorChain,
    normalizeApiKey,
    rootCauseMessage,
)
from foundry_studio.llm.providers.openai_compat import OpenAICompatibleProvider
from foundry_studio.llm.registry import LLMRegistry

PLAN_JSON = (
    '{"model": "rfd3", "name": "Mock design", "params": {"contigs": "A1-50", "n_batches": 3}, '
    '"resources": {"gres": "gpu:1"}, "invocation": {}, "warnings": [], "missing_inputs": []}'
)


def _make_fake_provider(plan_json: str = PLAN_JSON) -> BaseLLMProvider:
    class FakeProvider(BaseLLMProvider):
        name = "mock"
        base_url = "http://mock"
        api_key_env = ""
        model = "gpt-4o-mini"

        async def stream(self, messages, model=None, temperature=0.0, **opts):
            full = plan_json
            mid = len(full) // 2
            yield full[:mid]
            yield full[mid:]

    return FakeProvider()


@pytest.fixture()
def fake_registry(monkeypatch):
    reg = LLMRegistry()
    reg.register("mock", _make_fake_provider())
    monkeypatch.setattr(
        "foundry_studio.agent.planner.build_registry", lambda settings: reg
    )
    monkeypatch.setattr(
        "foundry_studio.api.routes_agent.build_registry", lambda settings: reg
    )
    return reg


def parse_sse(text: str) -> list[dict]:
    """Parse an SSE byte stream into a list of {event, data} dicts."""
    events: list[dict] = []
    for block in text.split("\n\n"):
        ev = None
        data_parts: list[str] = []
        for line in block.splitlines():
            if line.startswith("event:"):
                ev = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data_parts.append(line[len("data:") :].strip())
        if ev is not None:
            events.append({"event": ev, "data": _json.loads("".join(data_parts))})
    return events


# --------------------------------------------------------------------------- #
# Provider (real SSE mock server)
# --------------------------------------------------------------------------- #
def _start_mock_sse_server(full_json: str, *, with_finish: bool = True):
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):  # noqa: D102
            pass

        def do_POST(self):  # noqa: N802
            n = int(self.headers.get("Content-Length", "0"))
            self.rfile.read(n)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            mid = len(full_json) // 2
            for i, chunk in enumerate((full_json[:mid], full_json[mid:])):
                choice: dict = {"delta": {"content": chunk}}
                if with_finish and i == 1:
                    choice["finish_reason"] = "stop"
                payload = _json.dumps({"choices": [choice]})
                self.wfile.write(f"data: {payload}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def test_openai_provider_streams_real_sse():
    server, url = _start_mock_sse_server(PLAN_JSON)
    try:
        provider = OpenAICompatibleProvider(name="mock", base_url=url, api_key_env="")

        async def run():
            text = await provider.complete([{"role": "user", "content": "hi"}])
            toks = [d async for d in provider.stream([{"role": "user", "content": "hi"}])]
            return text, toks

        text, toks = asyncio.run(run())
        assert "".join(toks) == PLAN_JSON
        assert '"model": "rfd3"' in text
    finally:
        server.shutdown()


def test_openai_provider_missing_key_raises():
    provider = OpenAICompatibleProvider(
        name="x", base_url="http://127.0.0.1:1", api_key_env="NO_SUCH_ENV_VAR_XYZ"
    )
    with pytest.raises(LLMError) as exc:
        asyncio.run(provider.complete([{"role": "user", "content": "hi"}]))
    assert exc.value.code == LLMError.MISSING_CREDENTIAL


# --------------------------------------------------------------------------- #
# Tier 4 deepseek-harness inspired primitives
# --------------------------------------------------------------------------- #
def test_error_chain_walks_cause_and_context():
    root = ConnectionError("ECONNREFUSED")
    mid = RuntimeError("fetch failed")
    mid.__cause__ = root
    outer = LLMError(LLMError.TRANSPORT, "provider down", cause=mid)
    chain = errorChain(outer)
    assert chain[0] is outer
    assert chain[-1] is root
    assert "ConnectionError" in rootCauseMessage(outer)


def test_normalize_api_key_rejects_bad_bytes():
    assert normalizeApiKey("sk-abc123") == "sk-abc123"
    with pytest.raises(LLMError) as exc:
        normalizeApiKey("sk has space")
    assert exc.value.code == LLMError.MISSING_CREDENTIAL
    with pytest.raises(LLMError):
        normalizeApiKey("sk-\nnewline")
    with pytest.raises(LLMError):
        normalizeApiKey("sk-键")  # non-ASCII


def test_token_usage_accumulator():
    u = TokenUsage(input_tokens=10, output_tokens=5) + TokenUsage(output_tokens=3, cached_tokens=2)
    assert u.input_tokens == 10
    assert u.output_tokens == 8
    assert u.cached_tokens == 2
    assert u.total == 18


def test_backoff_policy():
    cfg = BackoffConfig(max_retries=3, base_delay=1.0, max_delay=10.0, jitter=0.0)
    assert cfg.is_retryable(LLMError.RATE_LIMIT)
    assert not cfg.is_retryable(LLMError.AUTH)
    # base * 2^attempt, clamped at max_delay
    assert cfg.delay_for_attempt(0) == 1.0
    assert cfg.delay_for_attempt(1) == 2.0
    assert cfg.delay_for_attempt(2) == 4.0
    assert cfg.delay_for_attempt(5) == 10.0  # clamped
    # With jitter, the delay is within ±30% of the base.
    jittered = BackoffConfig(max_retries=2, base_delay=1.0, max_delay=10.0, jitter=0.3)
    for _ in range(50):
        d = jittered.delay_for_attempt(0)
        assert 0.7 <= d <= 1.3


def test_stream_chunks_emit_text_and_finish():
    server, url = _start_mock_sse_server(PLAN_JSON)
    try:
        provider = OpenAICompatibleProvider(name="mock", base_url=url, api_key_env="")

        async def run():
            chunks = []
            async for c in provider.stream_chunks(
                [{"role": "user", "content": "hi"}]
            ):
                chunks.append(c)
            return chunks

        chunks = asyncio.run(run())
        types = [c.type for c in chunks]
        assert "text" in types
        assert "finish" in types
        finish = next(c for c in chunks if c.type == "finish")
        assert finish.finish_reason == FinishReason.STOP
    finally:
        server.shutdown()


# --------------------------------------------------------------------------- #
# Planner
# --------------------------------------------------------------------------- #
def test_planner_resolve_uses_llm(fake_registry, settings):
    planner = Planner(settings=settings)
    plan = asyncio.run(planner.resolve("design with RFD3, sample 3 designs"))
    assert plan.model == "rfd3"
    assert plan.resolved_by == "llm"


def test_planner_stream_events(fake_registry, settings):
    planner = Planner(settings=settings)
    events: list[dict] = []

    async def collect():
        async for ev in planner.plan_stream("design with RFD3"):
            events.append(ev)

    asyncio.run(collect())
    types = [e["type"] for e in events]
    assert "token" in types
    assert events[-1]["type"] == "plan"
    assert events[-1]["plan"]["model"] == "rfd3"


def test_planner_falls_back_on_provider_error(settings, monkeypatch):
    class BadProvider(BaseLLMProvider):
        name = "bad"
        base_url = "http://x"
        api_key_env = ""

        async def stream(self, messages, model=None, temperature=0.0, **opts):
            raise LLMError(LLMError.AUTH, "unauthorized")
            yield  # noqa: UNREACHABLE

    reg = LLMRegistry()
    reg.register("bad", BadProvider())
    monkeypatch.setattr(
        "foundry_studio.agent.planner.build_registry", lambda s: reg
    )
    planner = Planner(settings=settings)
    plan = asyncio.run(planner.resolve("design with RFD3 sample 3"))
    assert plan.resolved_by == "heuristic"
    assert plan.model == "rfd3"
    assert any("llm planner unavailable" in w for w in plan.warnings)


# --------------------------------------------------------------------------- #
# API endpoints
# --------------------------------------------------------------------------- #
def test_chat_sse(client, fake_registry):
    res = client.post("/api/agent/chat", json={"message": "design with RFD3"})
    assert res.status_code == 200
    events = parse_sse(res.text)
    types = [e["event"] for e in events]
    assert "plan" in types
    plan = [e["data"] for e in events if e["event"] == "plan"][-1]
    assert plan["model"] == "rfd3"
    tokens = "".join(e["data"]["text"] for e in events if e["event"] == "token")
    assert tokens == PLAN_JSON


def test_run_uses_message(client, fake_registry):
    res = client.post(
        "/api/agent/run",
        json={"message": "design with RFD3", "engine_mode": "simulation"},
    )
    assert res.status_code == 201, res.text
    job = res.json()
    assert job["model"] == "rfd3"
    assert job["status"] in ("queued", "running", "succeeded")


def test_capabilities_lists_providers(client):
    res = client.get("/api/agent/capabilities")
    assert res.status_code == 200
    body = res.json()
    assert "providers" in body
    names = [p["name"] for p in body["providers"]]
    assert "openai" in names


def test_health_includes_llm(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert "llm" in body
    assert "providers" in body["llm"]


def test_chat_falls_back_heuristic_without_key(client, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    res = client.post("/api/agent/chat", json={"message": "design with RFD3 sample 3"})
    assert res.status_code == 200
    events = parse_sse(res.text)
    # No token events when the LLM is unavailable; only a heuristic plan.
    assert all(e["event"] != "token" for e in events)
    plan = [e["data"] for e in events if e["event"] == "plan"][-1]
    assert plan["model"] == "rfd3"
    assert plan["resolved_by"] == "heuristic"
