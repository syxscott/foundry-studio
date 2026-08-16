/** Typed fetch client for the foundry-studio API. */

import type {
  ApiErrorBody,
  CheckpointInfo,
  HealthResponse,
  Job,
  JobCreatePayload,
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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
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
    request<{ deleted: unknown[]; total_bytes: number; dry_run: boolean }>(
      "/checkpoints/clean",
      { method: "POST" },
    ),

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
};
