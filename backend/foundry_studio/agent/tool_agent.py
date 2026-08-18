"""Tool-capable agent — the Planner augmented with tool-calling ability.

This module provides :class:`ToolAgent`, which extends the text-only
:class:`Planner` with:

- Sending tool schemas to the LLM (OpenAI ``tools`` / Anthropic ``tools``)
- Parsing ``tool_call`` chunks from the stream
- Executing tools and injecting their results back into the conversation
- Yielding structured SSE events: ``token``, ``tool-call``, ``tool-result``, ``plan``
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

from foundry_studio.agent.planner import PlanResult
from foundry_studio.config import Settings
from foundry_studio.engines import models as model_catalog
from foundry_studio.llm import LLMError
from foundry_studio.llm.registry import build_registry
from foundry_studio.llm.transports import get_transport

MAX_TOOL_CALLS = 5  # hard cap to prevent runaway loops


class ToolAgent:
    """A Planner that can call tools during streaming.

    Parameters
    ----------
    settings : Settings
        Application settings (used to resolve the LLM provider).
    tools : list[dict]
        OpenAI-format tool schemas to expose to the LLM.
    api_key / base_url / model / api_format
        Per-request credential overrides (same as :class:`Planner`).
    max_tool_calls : int
        Maximum tool calls before forcing a final plan (default 5).
    """

    def __init__(
        self,
        settings: Settings,
        tools: list[dict],
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        api_format: str | None = None,
        max_tool_calls: int = MAX_TOOL_CALLS,
    ) -> None:
        self.settings = settings
        self.tools = tools
        self.api_key = api_key
        self.base_url = base_url
        self.model_override = model
        self.api_format = api_format
        self.max_tool_calls = max_tool_calls

    # ------------------------------------------------------------------ #
    # Public entry point                                                   #
    # ------------------------------------------------------------------ #

    async def run(
        self, message: str
    ) -> AsyncIterator[dict[str, Any]]:
        """Run the tool-capable agent on *message*.

        Yields SSE-compatible dicts.  Caller wraps them with ``_sse(event, data)``.
        """
        messages = self._build_messages(message)

        # Collect tool calls and results across the loop
        tool_calls: list[dict] = []
        accumulated_text: list[str] = []

        # Resolve provider and transport
        api_mode = self._resolve_api_mode()
        transport_cls = get_transport(api_mode)
        if transport_cls is None:
            yield {"type": "error", "message": f"no transport for api_mode: {api_mode}"}
            return

        transport = self._build_transport(transport_cls)

        iteration = 0
        while iteration < self.max_tool_calls:
            iteration += 1

            # Stream from the transport; tools only on the first turn
            tools_this_turn = self.tools if iteration == 1 else None
            async for chunk in transport.stream(
                messages,
                tools_this_turn,
                api_key=self.api_key,
                model=self.model_override,
            ):
                if chunk.type == "text" and chunk.text:
                    accumulated_text.append(chunk.text)
                    yield {"type": "token", "text": chunk.text}

                elif chunk.type == "tool_call":
                    tc_id = chunk.tool_call_id or f"call_{uuid.uuid4().hex[:8]}"
                    tc_name = chunk.tool_call_name or ""
                    tc_args_str = chunk.tool_call_arguments or ""

                    # Skip partial JSON arguments and nameless calls
                    if tc_name == "__partial__" or not tc_name:
                        continue

                    # Parse JSON arguments
                    try:
                        args = json.loads(tc_args_str) if tc_args_str else {}
                    except json.JSONDecodeError:
                        args = {}

                    tool_calls.append({"id": tc_id, "name": tc_name, "arguments": args})
                    yield {
                        "type": "tool-call",
                        "toolCallId": tc_id,
                        "toolName": tc_name,
                        "arguments": args,
                    }

                elif chunk.type == "finish":
                    break

            # If no tool calls this turn, we're done
            if not tool_calls:
                break

            # Execute the most recent tool call
            last_tc = tool_calls[-1]
            result = await self._execute_tool(last_tc["name"], last_tc["arguments"])

            ok = result.get("ok", False)
            yield {
                "type": "tool-result",
                "toolCallId": last_tc["id"],
                "ok": ok,
                "result": result.get("result"),
                "error": result.get("error"),
            }

            # Append the assistant turn with tool calls, then the tool result
            assistant_content = "".join(accumulated_text)
            messages.append({
                "role": "assistant",
                "content": assistant_content,
                "tool_calls": [
                    {"id": tc["id"], "function": {"name": tc["name"], "arguments": json.dumps(tc["arguments"])}}
                    for tc in tool_calls
                ],
            })
            messages.append({
                "role": "tool",
                "tool_call_id": last_tc["id"],
                "content": json.dumps(result),
            })

            # Reset text buffer for next assistant turn
            accumulated_text = []

        # Try to parse a plan from accumulated text
        plan = self._parse_plan("".join(accumulated_text))
        if plan:
            yield {"type": "plan", "plan": plan.to_dict()}
        elif accumulated_text:
            yield {"type": "error", "message": "LLM response did not contain a valid plan"}
        else:
            yield {"type": "error", "message": "LLM returned no text"}

    # ------------------------------------------------------------------ #
    # Message building                                                     #
    # ------------------------------------------------------------------ #

    def _build_messages(self, message: str) -> list[dict]:
        catalog_lines = []
        for m in model_catalog.all_models():
            caps = m.get("capabilities", [])
            catalog_lines.append(
                f"- {m['id']}: {m.get('name', '')} — capabilities: {', '.join(caps)}"
            )
        catalog = "\n".join(catalog_lines)

        tools_description = "\n".join(
            f"- **{s['function']['name']}**: {s['function'].get('description', '')}"
            for s in self.tools
        )

        system = (
            "You are the planning agent for foundry-studio, a control surface for the "
            "RosettaCommons Foundry protein-design toolkit (RFD3, RFD3NA, RF3, "
            "ProteinMPNN). Given a natural-language experiment description, first decide "
            "if you need to call any tools to gather information before producing a plan.\n"
            "Available tools:\n"
            f"{tools_description}\n"
            "If you call tools, wait for results before continuing. When you have enough "
            "information, output a JSON plan object with these keys:\n"
            "  model: one of [rfd3, rfd3na, rf3, mpnn]\n"
            "  name: short job name (string)\n"
            "  params: object of model parameters\n"
            "  resources: object with optional keys gres, account, partition, time\n"
            "  invocation: object (usually {})\n"
            "  warnings: array of strings\n"
            "  missing_inputs: array of strings\n"
            "Available models:\n"
            f"{catalog}\n"
            "Only output the JSON object. Do not wrap it in markdown fences."
        )
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": message},
        ]

    # ------------------------------------------------------------------ #
    # Helpers                                                             #
    # ------------------------------------------------------------------ #

    def _resolve_api_mode(self) -> str:
        fmt = (self.api_format or "").strip()
        if fmt == "anthropic":
            return "anthropic_messages"
        return "chat_completions"

    def _build_transport(self, transport_cls):
        reg = build_registry(self.settings)
        provider = reg.default_provider()
        if provider is None:
            raise LLMError(LLMError.MISSING_CREDENTIAL, "no LLM provider")
        return transport_cls(
            name=provider.name,
            base_url=provider.base_url,
            api_key_env=getattr(provider, "api_key_env", ""),
            model=self.model_override or provider.model,
            timeout=provider.timeout,
            retry=provider.retry,
        )

    async def _execute_tool(self, name: str, arguments: dict) -> dict:
        from foundry_studio.tools import ToolRegistry

        return await ToolRegistry.execute_tool(name, arguments)

    def _parse_plan(self, raw: str) -> PlanResult | None:
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        blob = raw[start : end + 1]
        try:
            data = json.loads(blob)
        except json.JSONDecodeError:
            return None
        model = data.get("model")
        if model is None or model_catalog.get_model(model) is None:
            return None
        return PlanResult(
            model=model,
            name=data.get("name", "") or f"{model} agent job",
            params=data.get("params", {}) or {},
            resources=data.get("resources", {}) or {},
            invocation=data.get("invocation", {}) or {},
            warnings=list(data.get("warnings", []) or []),
            missing_inputs=list(data.get("missing_inputs", []) or []),
            resolved_by="llm",
        )
