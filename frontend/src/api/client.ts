/** Typed fetch client for the foundry-studio API. */

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
   * `onToken`; the final structured plan via `onPlan`. Falls back gracefully: if
   * the LLM is unavailable the server still emits a single `plan` event (heuristic).
   * Errors carry an `i18nErrorKey` + `errorArgs` payload (when the server
   * provides one) so the UI can render the localized string from its own
   * catalog without parsing the human-readable `message`.
   */
  streamAgentChat: (
    message: string,
    lang: string,
    handlers: {
      onToken?: (text: string) => void;
      onPlan?: (plan: AgentPlan) => void;
      onDone?: () => void;
      onError?: (
        message: string,
        meta?: { i18nErrorKey?: string; errorArgs?: Record<string, unknown> },
      ) => void;
      signal?: AbortSignal;
    },
  ): void => {
    const cfg = api.llmConfig.get();
    let reader: ReadableStreamDefaultReader<Uint8Array> | null = null;
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
      }),
      signal: handlers.signal,
    })
      .then((res) => {
        if (!res.ok) {
          res
            .json()
            .then((body) =>
              handlers.onError?.(
                (body && (body.message || body.message_key)) ||
                  `HTTP ${res.status}`,
                body && (body.i18nErrorKey || body.message_key)
                  ? {
                      i18nErrorKey: body.i18nErrorKey || body.message_key,
                      errorArgs: body.errorArgs || body.params,
                    }
                  : undefined,
              ),
            )
            .catch(() => handlers.onError?.(`HTTP ${res.status}`));
          return;
        }
        if (!res.body) {
          handlers.onError?.("No response stream");
          return;
        }
        reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buf = "";
        const pump = (): Promise<void> =>
          reader!.read().then(({ done, value }) => {
            if (done) {
              handlers.onDone?.();
              return;
            }
            buf += decoder.decode(value, { stream: true });
            let idx: number;
            while ((idx = buf.indexOf("\n\n")) >= 0) {
              const frame = buf.slice(0, idx);
              buf = buf.slice(idx + 2);
              const ev = parseSSEFrame(frame);
              if (!ev) continue;
              if (ev.event === "token" && ev.data && typeof ev.data.text === "string")
                handlers.onToken?.(ev.data.text);
              else if (ev.event === "plan" && ev.data) handlers.onPlan?.(ev.data as AgentPlan);
              else if (ev.event === "error") {
                handlers.onError?.(
                  (ev.data && (ev.data.message as string)) || "error",
                  ev.data && (ev.data.i18nErrorKey || ev.data.message_key)
                    ? {
                        i18nErrorKey:
                          (ev.data.i18nErrorKey as string) ||
                          (ev.data.message_key as string),
                        errorArgs: (ev.data.errorArgs as Record<string, unknown>) ||
                          (ev.data.params as Record<string, unknown>),
                      }
                    : undefined,
                );
              }
            }
            return pump();
          });
        return pump();
      })
      .catch((e: unknown) => {
        if (e instanceof DOMException && e.name === "AbortError") {
          if (reader) {
            reader.cancel().catch(() => {});
          }
          return;
        }
        handlers.onError?.(String(e));
      });
  },

  agentRun: (payload: AgentRunPayload) =>
    request<Job>("/agent/run", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};

/** Parse one SSE frame (`event:` / `data:` lines) into {event, data}. */
function parseSSEFrame(
  frame: string,
): {
  event: string;
  data:
    | {
        text?: string;
        message?: string;
        i18nErrorKey?: string;
        message_key?: string;
        errorArgs?: Record<string, unknown>;
        params?: Record<string, unknown>;
      }
    | null;
} | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of frame.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  if (dataLines.length === 0) return null;
  try {
    return { event, data: JSON.parse(dataLines.join("")) };
  } catch {
    return { event, data: null };
  }
}
