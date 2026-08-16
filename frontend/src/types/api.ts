/** Shared API types mirroring the backend Pydantic schemas. */

export type ModelId = "rfd3" | "rfd3na" | "rf3" | "mpnn";
export type JobStatus = "draft" | "queued" | "running" | "succeeded" | "failed" | "canceled";
export type EngineMode = "auto" | "real" | "simulation";

export interface ModelInfo {
  id: ModelId;
  name: string;
  name_key?: string;
  description: string;
  description_key?: string;
  capabilities: string[];
  capability_keys?: string[];
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

export interface BackendInfo {
  active_backend: string;
  scheduler: string;
  transport: string;
  configured: boolean;
  agent_enabled: boolean;
}

export interface HealthResponse {
  status: string;
  version: string;
  engine_mode: string;
  simulation_fallback: boolean;
  gpu_available: boolean;
  foundry_available: boolean;
  data_dir: string;
  backend: BackendInfo;
  workers: { model: string; pid: number; alive: boolean; exit_code?: number | null }[];
  llm?: { providers: LlmProviderStatus[] } | null;
  message?: string | null;
}

export interface LlmProviderStatus {
  name: string;
  base_url: string;
  model: string | null;
  api_key_env: string;
  key_present: boolean;
  configured: boolean;
}

export interface AgentCapabilities {
  version: string;
  backend: BackendInfo;
  providers: LlmProviderStatus[];
  models: {
    id: string;
    name: string | null;
    capabilities: string[];
    accepted_extensions: string[];
    param_schema: Record<string, unknown>;
  }[];
}

export interface AgentPlan {
  model: string;
  name: string;
  params: Record<string, unknown>;
  resources: Record<string, unknown>;
  invocation: Record<string, unknown>;
  warnings: string[];
  missing_inputs: string[];
  resolved_by: string;
}

export interface AgentChatResponse extends AgentPlan {}

export interface AgentRunPayload {
  model?: string;
  message?: string;
  name?: string;
  params?: Record<string, unknown>;
  input_files?: { role: string; filename: string; name?: string }[];
  resources?: Record<string, unknown>;
  invocation?: Record<string, unknown>;
  engine_mode?: string;
  lang?: string;
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
  // HPC / agent tracking — for correlating a local job with the scheduler job.
  remote_job_id?: string | null;
  backend?: string | null;
  scheduler?: string | null;
  job_spec?: Record<string, unknown> | null;
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
