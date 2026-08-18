/** Typed fetch client for the foundry-studio API. */

import { EventSourceParserStream } from "eventsource-parser/stream";

import type {
  AgentCapabilities,
  AgentPlan,
  AgentRunPayload,
  ApiErrorBody,
  CheckpointInfo,
  HealthResponse,
  Job,
  JobCreatePayload,
  LlmConfig,
  LlmSettingsResponse,
  ModelInfo,
} from "../types/api";

const BASE = "/api";

export class ApiClientError extends Error {
  body: ApiErrorBody;
  status: number;

  constructor(status: number, body: ApiErrorBody) {
    super(body.message || body.message_key || `HTTP ${status}`);
    this.name = "ApiClientError";
    this.status = status;
    this.body = body;
  }
}

async function request<T>(path: string, init?: RequestInit, timeoutMs = 30000): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${BASE}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...init,
      signal: controller.signal,
    });
    clearTimeout(timeout);
    if (!res.ok) {
      let body: ApiErrorBody;
      try {
        body = (await res.json()) as ApiErrorBody;
      } catch {
        body = {
          message_key: "error.unknown",
          params: { detail: await res.text().catch(() => "") },
          message: `HTTP ${res.status}`,
        };
      }
      throw new ApiClientError(res.status, body);
    }
    return (await res.json()) as T;
  } catch (e) {
    clearTimeout(timeout);
    throw e;
  }
}

export const api = {
  health: () => request<HealthResponse>("/health"),

  models: () => request<ModelInfo[]>("/models"),

  checkpoints: () => request<CheckpointInfo[]>("/checkpoints"),
  installCheckpoint: (name: string) =>
    request<CheckpointInfo>(`/checkpoints/install?name=${encodeURIComponent(name)}`, {
      method: "POST",
    }),
  cleanCheckpoints: () =>
    request<{ deleted: unknown[]; total_bytes: number; dry_run: boolean; search_dirs: string[]; install_dir: string }>(
      "/checkpoints/clean",
      { method: "POST" },
    ),

  llmSettings: () => request<LlmSettingsResponse>("/settings/llm"),

  llmConfig: {
    storageKey: "foundry-studio-llm-config",
    get(): LlmConfig {
      try {
        const raw = localStorage.getItem(this.storageKey);
        if (raw) {
          const cfg = JSON.parse(raw) as LlmConfig;
          // Backfill apiFormat for configs saved before this field existed
          if (!cfg.apiFormat) cfg.apiFormat = "openai_chat";
          return cfg;
        }
        return { provider: "openai", baseUrl: "https://api.openai.com/v1", model: "gpt-5.6-luna", apiKey: "", apiFormat: "openai_chat" };
      } catch { return { provider: "openai", baseUrl: "https://api.openai.com/v1", model: "gpt-5.6-luna", apiKey: "", apiFormat: "openai_chat" }; }
    },
    set(cfg: LlmConfig): void {
      try { localStorage.setItem(this.storageKey, JSON.stringify(cfg)); } catch { /* quota exceeded */ }
    },
  },

  createJob: (payload: JobCreatePayload) =>
    request<Job>("/jobs", { method: "POST", body: JSON.stringify(payload) }),

  listJobs: (status?: string) =>
    request<{ items: Job[]; total: number }>(
      `/jobs${status ? `?status=${status}` : ""}`,
    ),

  getJob: (id: string) => request<Job>(`/jobs/${id}`),

  submitJob: (id: string) =>
    request<Job>(`/jobs/${id}/submit`, { method: "POST" }),

  cancelJob: (id: string) =>
    request<{ job_id: string; canceled: boolean; status: string }>(
      `/jobs/${id}/cancel`,
      { method: "POST" },
    ),

  deleteJob: (id: string) =>
    request<{ ok: boolean; job_id: string }>(`/jobs/${id}`, { method: "DELETE" }),

  getLogs: (id: string) =>
    request<{ job_id: string; logs: string }>(`/jobs/${id}/logs`),

  downloadJobZip: (id: string) => `${BASE}/jobs/${id}/download-zip`,

  uploadFiles: async (
    jobId: string,
    files: File[],
    role: string,
  ): Promise<{ job_id: string; uploaded: { role: string; filename: string; name: string }[]; errors: { filename: string; error: string; detail: string }[] }> => {
    const form = new FormData();
    for (const f of files) form.append("files", f);
    form.append("role", role);
    const res = await fetch(`${BASE}/jobs/${jobId}/files`, {
      method: "POST",
      body: form,
    });
    if (!res.ok) {
      const body = (await res.json().catch(() => null)) as ApiErrorBody | null;
      throw new ApiClientError(res.status, body ?? { message_key: "error.upload_failed", params: {}, message: `HTTP ${res.status}` });
    }
    return (await res.json()) as { job_id: string; uploaded: { role: string; filename: string; name: string }[]; errors: { filename: string; error: string; detail: string }[] };
  },

  // --- Agent surface (Control API) -------------------------------------------
  agentCapabilities: () => request<AgentCapabilities>("/agent/capabilities"),

  /**
   * Stream the agent chat endpoint (Server-Sent Events). Token deltas arrive via
   * `onToken`; tool calls via `onToolCall` / `onToolResult`; the final
   * structured plan via `onPlan`. Falls back gracefully: if the LLM is unavailable
   * the server still emits a single `plan` event (heuristic).
   *
   * Errors carry an `i18nErrorKey` + `errorArgs` payload (when the server
   * provides one) so the UI can render the localized string from its own
   * catalog without parsing the human-readable `message`.
   *
   * Retry policy: up to 2 retries with exponential backoff + jitter for transient
   * server errors (5xx). AbortError is handled gracefully (no retry).
   */
  streamAgentChat: (
    message: string,
    lang: string,
    handlers: {
      onToken?: (text: string) => void;
      onToolCall?: (payload: { toolCallId: string; toolName: string; arguments: Record<string, unknown> }) => void;
      onToolResult?: (payload: { toolCallId: string; ok: boolean; result?: unknown; error?: string }) => void;
      onPlan?: (plan: AgentPlan) => void;
      onDone?: () => void;
      onError?: (
        message: string,
        meta?: { i18nErrorKey?: string; errorArgs?: Record<string, unknown> },
      ) => void;
      signal?: AbortSignal;
    },
    tools?: { type: "function"; function: { name: string; description?: string; parameters: Record<string, unknown> } }[],
  ): void => {
    const cfg = api.llmConfig.get();

    const doFetch = (retries: number): void => {
      let readerRef: ReadableStreamDefaultReader<Uint8Array> | null = null;
      let aborted = false;

      const cleanup = () => {
        if (readerRef) {
          readerRef.cancel().catch(() => {});
          readerRef = null;
        }
      };

      // Wrap signal so we can detect abort without killing the outer fetch
      const innerController = new AbortController();
      const fusedSignal = handlers.signal
        ? (() => {
            const c = new AbortController();
            handlers.signal!.addEventListener("abort", () => {
              aborted = true;
              c.abort();
              cleanup();
            });
            return c.signal;
          })()
        : innerController.signal;

      fetch(`${BASE}/agent/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message,
          lang,
          api_key: cfg.apiKey || undefined,
          base_url: cfg.baseUrl || undefined,
          model: cfg.model || undefined,
          api_format: cfg.apiFormat || undefined,
          tools: tools ?? undefined,
        }),
        signal: fusedSignal,
      })
        .then(async (res) => {
          if (!res.ok) {
            // 5xx: retry with backoff; 4xx: never retry
            if (res.status >= 500 && retries > 0) {
              const delay = _retryDelay(retries);
              await _sleep(delay);
              doFetch(retries - 1);
              return;
            }
            let errKey: string | undefined;
            let errArgs: Record<string, unknown> | undefined;
            let errMsg = `HTTP ${res.status}`;
            try {
              const body = await res.json();
              errMsg = body.message || body.message_key || errMsg;
              if (body.i18nErrorKey || body.message_key) {
                errKey = body.i18nErrorKey || body.message_key;
                errArgs = body.errorArgs || body.params;
              }
            } catch {
              // use HTTP status as message
            }
            handlers.onError?.(errMsg, errKey ? { i18nErrorKey: errKey, errorArgs: errArgs } : undefined);
            return;
          }

          if (!res.body) {
            handlers.onError?.("No response stream");
            return;
          }

          readerRef = res.body.getReader();

          // Use eventsource-parser for robust SSE framing:
          // - Handles UTF-8 continuation bytes correctly
          // - Handles CRLF, comment lines, chunk reassembly
          // - Dispatches on blank-line boundary
          const stream = res.body
            .pipeThrough(new TextDecoderStream())
            .pipeThrough(new EventSourceParserStream());

          const reader = stream.getReader();
          readerRef = null; // ownership transferred to eventsource-parser

          try {
            while (true) {
              if (aborted) break;
              const { done, value } = await reader.read();
              if (done || aborted) break;
              _handleSSEEvent(value as { event?: string; data?: string }, handlers);
            }
          } catch (e) {
            if (aborted) return;
            // If stream errors (e.g. truncated), retry if we have attempts left
            if (retries > 0) {
              const delay = _retryDelay(retries);
              await _sleep(delay);
              doFetch(retries - 1);
              return;
            }
            handlers.onError?.(String(e));
            return;
          }

          handlers.onDone?.();
        })
        .catch((e: unknown) => {
          if (e instanceof DOMException && e.name === "AbortError") {
            cleanup();
            return;
          }
          // Network / fetch failures: retry if attempts remain
          if (retries > 0) {
            _sleep(_retryDelay(retries)).then(() => {
              if (!aborted) doFetch(retries - 1);
            });
            return;
          }
          handlers.onError?.(String(e));
        });
    };

    doFetch(2); // 2 retries
  },

  agentRun: (payload: AgentRunPayload) =>
    request<Job>("/agent/run", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};

/** Handle one parsed SSE event from eventsource-parser. */
function _handleSSEEvent(
  ev: { event?: string; data?: string },
  handlers: {
    onToken?: (text: string) => void;
    onToolCall?: (payload: { toolCallId: string; toolName: string; arguments: Record<string, unknown> }) => void;
    onToolResult?: (payload: { toolCallId: string; ok: boolean; result?: unknown; error?: string }) => void;
    onPlan?: (plan: AgentPlan) => void;
    onError?: (
      message: string,
      meta?: { i18nErrorKey?: string; errorArgs?: Record<string, unknown> },
    ) => void;
  },
): void {
  const event = ev.event || "message";
  let data: unknown;
  try {
    data = ev.data ? JSON.parse(ev.data) : null;
  } catch {
    data = null;
  }

  if (event === "token" && data && typeof (data as { text?: string }).text === "string") {
    handlers.onToken?.((data as { text: string }).text);
  } else if (event === "tool-call" && data) {
    const d = data as { toolCallId?: string; toolName?: string; arguments?: Record<string, unknown> };
    handlers.onToolCall?.({ toolCallId: d.toolCallId ?? "", toolName: d.toolName ?? "", arguments: d.arguments ?? {} });
  } else if (event === "tool-result" && data) {
    const d = data as { toolCallId?: string; ok?: boolean; result?: unknown; error?: string };
    handlers.onToolResult?.({ toolCallId: d.toolCallId ?? "", ok: d.ok ?? false, result: d.result, error: d.error });
  } else if (event === "plan" && data) {
    handlers.onPlan?.(data as AgentPlan);
  } else if (event === "error") {
    const d = data as { message?: string; i18nErrorKey?: string; message_key?: string; errorArgs?: Record<string, unknown>; params?: Record<string, unknown> } | null;
    handlers.onError?.(
      (d?.message as string) || "error",
      d && (d.i18nErrorKey || d.message_key)
        ? {
            i18nErrorKey: (d.i18nErrorKey as string) || (d.message_key as string),
            errorArgs: d.errorArgs || d.params,
          }
        : undefined,
    );
  }
}

/** Compute delay with exponential backoff + jitter (mirrors deepseek-harness llm-retry). */
function _retryDelay(attempt: number): number {
  // attempt: 2 → first retry (500ms base), 1 → second retry (1000ms)
  const base = 500;
  const exponential = Math.min(base * 2 ** (3 - attempt), 8000);
  const jitter = exponential * 0.3 * (Math.random() * 2 - 1);
  return Math.max(0, exponential + jitter);
}

function _sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

