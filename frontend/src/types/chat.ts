/** Part-based chat message model — mirrors hermes-agent's ChatMessagePart system. */

export type ChatMessagePart =
  | { type: "text"; text: string }
  | { type: "reasoning"; text: string }
  | {
      type: "tool-call";
      toolCallId: string;
      toolName: string;
      args: Record<string, unknown>;
      status: "pending" | "running" | "done" | "error";
      result?: unknown;
    }
  | { type: "plan"; plan: AgentPlan };

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system" | "tool";
  parts: ChatMessagePart[];
  timestamp?: number;
}

// -------------------------------------------------------------------------- //
// Utility functions (mirrors hermes-agent patterns)                        //
// -------------------------------------------------------------------------- //

/** Append a text delta to the last text part, or create a new one. */
export function appendTextPart(parts: ChatMessagePart[], delta: string): ChatMessagePart[] {
  const existing = parts[parts.length - 1];
  if (existing?.type === "text") {
    return [...parts.slice(0, -1), { type: "text", text: existing.text + delta }];
  }
  return [...parts, { type: "text", text: delta }];
}

/** Append a reasoning delta to the last reasoning part, or create a new one. */
export function appendReasoningPart(parts: ChatMessagePart[], delta: string): ChatMessagePart[] {
  const existing = parts[parts.length - 1];
  if (existing?.type === "reasoning") {
    return [...parts.slice(0, -1), { type: "reasoning", text: existing.text + delta }];
  }
  return [...parts, { type: "reasoning", text: delta }];
}

/** Upsert (update or insert) a tool-call part by toolCallId. */
export function upsertToolPart(
  parts: ChatMessagePart[],
  payload: {
    toolCallId: string;
    toolName?: string;
    args?: Record<string, unknown>;
    status?: "pending" | "running" | "done" | "error";
    result?: unknown;
  },
): ChatMessagePart[] {
  const idx = parts.findIndex(
    (p) => p.type === "tool-call" && p.toolCallId === payload.toolCallId,
  );
  if (idx >= 0) {
    const existing = parts[idx] as Extract<ChatMessagePart, { type: "tool-call" }>;
    return [
      ...parts.slice(0, idx),
      {
        ...existing,
        toolName: payload.toolName ?? existing.toolName,
        args: payload.args ?? existing.args,
        status: payload.status ?? existing.status,
        result: payload.result ?? existing.result,
      } as ChatMessagePart,
      ...parts.slice(idx + 1),
    ];
  }
  return [
    ...parts,
    {
      type: "tool-call",
      toolCallId: payload.toolCallId,
      toolName: payload.toolName ?? "",
      args: payload.args ?? {},
      status: payload.status ?? "pending",
      result: payload.result,
    },
  ];
}

// Re-export AgentPlan for convenience
import type { AgentPlan } from "./api";
export type { AgentPlan };
