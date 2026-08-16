/** Shared API types mirroring the backend Pydantic schemas. */

export type ModelId = "rfd3" | "rfd3na" | "rf3" | "mpnn";
export type JobStatus = "draft" | "queued" | "running" | "succeeded" | "failed" | "canceled";
export type EngineMode = "auto" | "real" | "simulation";

export interface ModelInfo {
  id: ModelId;
  name: string;
  description: string;
  capabilities: string[];
  param_schema: Record<string, unknown>;
  param_defaults: Record<string, unknown>;
  accepted_extensions: string[];
  requires_checkpoint: boolean;
  available_engines: string[];
  effective_engine: "real" | "simulation" | null;
  checkpoint_state: "installed" | "missing" | "unknown";
  real_engine_reason?: string;
}

export interface CheckpointInfo {
  name: string;
  filename: string;
  description: string;
  installed: boolean;
  path?: string | null;
  size_bytes?: number | null;
  url?: string | null;
}

export interface HealthResponse {
  status: string;
  version: string;
  engine_mode: string;
  simulation_fallback: boolean;
  gpu_available: boolean;
  foundry_available: boolean;
  data_dir: string;
  workers: { model: string; pid: number; alive: boolean; exit_code?: number | null }[];
  message?: string | null;
}

export interface OutputFile {
  name: string;
  kind: string;
  url: string;
  size_bytes: number;
}

export interface Job {
  id: string;
  model: ModelId;
  name: string;
  status: JobStatus;
  params: Record<string, unknown>;
  input_files: { role: string; filename: string; name: string }[];
  engine_mode: EngineMode;
  progress: number | null;
  error_code?: string | null;
  error_detail?: string | null;
  cancel_requested: boolean;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  outputs: OutputFile[];
  logs_url?: string | null;
}

export interface JobCreatePayload {
  model: string;
  name?: string;
  params: Record<string, unknown>;
  input_files?: { role: string; filename: string; name: string }[];
  engine_mode?: EngineMode;
}

export interface ApiErrorBody {
  message_key: string;
  params: Record<string, string>;
  message: string;
  detail?: string | null;
}

export interface I18nMessages {
  [key: string]: { zh: string; en: string; ja: string; ru: string };
}
