"""Regression tests for bugs found in the third-party LLM integration audit.

Each test pins one defect that was actually reproduced before the fix, so a
future refactor cannot silently reintroduce it.
"""

from __future__ import annotations

import asyncio
import json as _json
import threading
import http.server

import pytest

from foundry_studio.agent.planner import Planner
from foundry_studio.agent.tool_agent import ToolAgent
from foundry_studio.config import Settings
from foundry_studio.llm.registry import LLMRegistry
from foundry_studio.llm.transports import get_transport
from foundry_studio.tools.registry import ToolRegistry


# --------------------------------------------------------------------------- #
# 1. Per-request base_url must actually reach the provider
# --------------------------------------------------------------------------- #
def test_planner_override_keeps_settings_timeout_and_retry():
    s = Settings(agent_llm_timeout=300.0, agent_llm_retry=7)
    p = Planner(settings=s, base_url="http://example.invalid/v1", model="m")
    prov = p._registry().default_provider()
    assert prov is not None
    # Regression: the override used to reset to the 60 s / 2-retry defaults.
    assert prov.timeout == 300.0
    assert prov.retry == 7


def test_planner_override_honours_settings_api_format():
    s = Settings(agent_llm_api_format="anthropic")
    p = Planner(settings=s, base_url="http://example.invalid", model="m")
    prov = p._registry().default_provider()
    # Regression: an Anthropic-configured install was handed an
    # OpenAI-compatible provider, so every request used the wrong wire format.
    assert type(prov).__name__ == "AnthropicProvider"


def test_registry_replace_is_public_and_isolated():
    """Planner used to poke ``reg._providers.clear()`` directly."""
    reg = LLMRegistry()
    s = Settings()
    from foundry_studio.llm.providers.openai_compat import OpenAICompatibleProvider

    reg.replace("override", OpenAICompatibleProvider(name="o", base_url="http://x/v1"))
    assert [p["name"] for p in reg.summaries()] == ["override"]


def test_toolagent_transport_uses_request_base_url():
    s = Settings(agent_llm_base_url="https://api.openai.com/v1")
    a = ToolAgent(settings=s, tools=[], base_url="http://127.0.0.1:9/v1", model="m")
    t = a._build_transport(get_transport("chat_completions"))
    # Regression: the override was ignored and traffic went to api.openai.com.
    assert t.base_url == "http://127.0.0.1:9/v1"


def test_toolagent_resolves_api_mode_from_settings():
    s = Settings(agent_llm_api_format="anthropic")
    a = ToolAgent(settings=s, tools=[])
    # Regression: only the per-request api_format was considered.
    assert a._resolve_api_mode() == "anthropic_messages"


# --------------------------------------------------------------------------- #
# 2. The SSE stream must always terminate with `done`
# --------------------------------------------------------------------------- #
def _sse_provider(final_text: str, tools: bool = False):
    """Mock provider: first turn (tools) emits a tool_call, second emits text."""

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):  # noqa: D102
            pass

        def do_POST(self):  # noqa: N802
            n = int(self.headers.get("Content-Length", "0"))
            body = _json.loads(self.rfile.read(n))
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            if tools and "tools" in body:
                frame = {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": "call_abc",
                                        "type": "function",
                                        "function": {
                                            "name": "list_models",
                                            "arguments": "{}",
                                        },
                                    }
                                ]
                            }
                        }
                    ]
                }
                self.wfile.write(f"data: {_json.dumps(frame)}\n\n".encode())
                self.wfile.write(b"data: [DONE]\n\n")
                return
            half = len(final_text) // 2
            for chunk in (final_text[:half], final_text[half:]):
                payload = {"choices": [{"delta": {"content": chunk}}]}
                self.wfile.write(f"data: {_json.dumps(payload)}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


PLAN = (
    '{"model":"rfd3","name":"T","params":{"contigs":"A1-40"},'
    '"resources":{},"invocation":{},"warnings":[],"missing_inputs":[]}'
)


def _parse_sse(text: str) -> list[tuple[str, dict]]:
    out: list[tuple[str, dict]] = []
    for block in text.split("\n\n"):
        name, data = None, []
        for line in block.splitlines():
            if line.startswith("event:"):
                name = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data.append(line[len("data:") :].strip())
        if name:
            out.append((name, _json.loads("".join(data))))
    return out


def _client_for(settings):
    from fastapi.testclient import TestClient

    from foundry_studio.app import create_app

    return TestClient(create_app(settings=settings))


def test_tool_loop_executes_once_then_plans(tmp_path):
    """Regression: tool_calls was never cleared, so the loop re-ran the same
    tool 5x (hitting max_tool_calls) and the plan text was thrown away."""
    server, url = _sse_provider(PLAN, tools=True)
    try:
        s = Settings(
            data_dir=tmp_path / "d",
            agent_llm_provider="openai",
            agent_llm_model="m",
            agent_llm_api_key_env="",
        )
        c = _client_for(s)
        res = c.post(
            "/api/agent/chat",
            json={
                "message": "design with RFD3",
                "base_url": url,
                "tools": ToolRegistry.get_all_schemas(),
            },
        )
        evs = _parse_sse(res.text)
        names = [n for n, _ in evs]
        assert names.count("tool-call") == 1, names
        assert names.count("tool-result") == 1, names
        assert "plan" in names
        assert names[-1] == "done"
        assert "error" not in names
    finally:
        server.shutdown()


def test_stream_always_ends_with_done_on_error(tmp_path):
    """Regression: the SSE helper `return`ed after an error, skipping `done`
    so the client kept its 'streaming' state forever."""
    s = Settings(data_dir=tmp_path / "d", agent_llm_provider="")
    c = _client_for(s)
    res = c.post("/api/agent/chat", json={"message": "xyzzy unparseable request"})
    evs = _parse_sse(res.text)
    names = [n for n, _ in evs]
    assert names[-1] == "done", names
    assert "error" in names


def test_stream_error_carries_detail_arg(tmp_path):
    """Regression: errorArgs was {} so `{{detail}}` rendered empty."""
    s = Settings(data_dir=tmp_path / "d", agent_llm_provider="")
    c = _client_for(s)
    res = c.post("/api/agent/chat", json={"message": "xyzzy unparseable request"})
    err = [d for n, d in _parse_sse(res.text) if n == "error"][0]
    assert err["errorArgs"]["detail"], err
    assert err["i18nErrorKey"] == "error.agent_cannot_parse"


def test_plan_stream_heuristic_only_error_is_terminal():
    s = Settings(agent_llm_provider="")
    planner = Planner(settings=s)

    async def collect():
        return [ev async for ev in planner.plan_stream("xyzzy unparseable")]

    events = asyncio.run(collect())
    # Regression: the generator raised ValueError out of the async iterator.
    assert events[-1]["type"] == "error"


def test_toolagent_without_provider_yields_error():
    s = Settings(agent_llm_provider="")
    agent = ToolAgent(settings=s, tools=[])

    async def collect():
        return [ev async for ev in agent.run("design with RFD3")]

    events = asyncio.run(collect())
    # Regression: LLMError escaped the generator uncaught.
    assert events[-1]["type"] == "error"


# --------------------------------------------------------------------------- #
# 3. Tool availability checks must not require an event loop
# --------------------------------------------------------------------------- #
def test_check_availability_works_without_event_loop():
    """Regression: `asyncio.get_event_loop()` raised RuntimeError in the
    threadpool that serves the sync `/capabilities` endpoint as soon as any
    tool registered a check_fn."""
    ToolRegistry._check_cache.clear()
    ToolRegistry.register(
        "__audit_probe__",
        {"type": "function", "function": {"name": "__audit_probe__", "parameters": {}}},
        lambda: None,
        check_fn=lambda: True,
    )
    try:
        out: dict = {}
        th = threading.Thread(target=lambda: out.update(ok=ToolRegistry.get_checks()))
        th.start()
        th.join(timeout=5)
        assert not th.is_alive()
        assert out.get("ok") is not None
        assert out["ok"]["__audit_probe__"] is True
    finally:
        ToolRegistry._tools.pop("__audit_probe__", None)
        ToolRegistry._check_cache.clear()


# --------------------------------------------------------------------------- #
# 4. Validation errors must stay in the localized envelope
# --------------------------------------------------------------------------- #
def test_unknown_model_returns_localized_404(client):
    res = client.post("/api/jobs", json={"model": "nope", "params": {}})
    # Regression: Pydantic's Literal rejected it with a bare 422 detail.
    assert res.status_code == 404
    body = res.json()
    assert body["message_key"] == "error.model_not_found"
    assert "Unknown model" in body["message"]
