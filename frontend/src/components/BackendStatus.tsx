import { useTranslation } from "react-i18next";

import type { BackendInfo } from "../types/api";

const BACKEND_LABEL: Record<string, string> = {
  local: "Local",
  slurm: "SLURM",
  pbs: "PBS",
  lsf: "LSF",
};

export default function BackendStatus({ info }: { info: BackendInfo | null }) {
  const { t } = useTranslation();
  if (!info) {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs text-slate-400">
        <span className="w-2 h-2 rounded-full bg-slate-300" />
        {t("backend.unknown")}
      </span>
    );
  }
  const configured = info.configured;
  return (
    <span className="inline-flex items-center gap-1.5 text-xs">
      <span
        className={`w-2 h-2 rounded-full ${configured ? "bg-emerald-500" : "bg-amber-400"}`}
      />
      <span className="font-medium text-slate-600">
        {BACKEND_LABEL[info.active_backend] ?? info.active_backend}
      </span>
      {info.active_backend !== "local" && (
        <span className="text-slate-400">· {info.transport}</span>
      )}
      <span
        className={`px-1.5 py-0.5 rounded-full text-[10px] font-medium ${
          configured ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"
        }`}
      >
        {configured ? t("backend.ready") : t("backend.notConfigured")}
      </span>
      {info.agent_enabled && (
        <span className="px-1.5 py-0.5 rounded-full text-[10px] font-medium bg-brand-50 text-brand-700">
          agent
        </span>
      )}
    </span>
  );
}
