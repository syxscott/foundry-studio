import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../api";
import AgentPanel from "../components/AgentPanel";
import BackendStatus from "../components/BackendStatus";
import ManualJobForm from "../components/ManualJobForm";
import { StatusBadge } from "../components/StatusBadge";
import type { BackendInfo, HealthResponse, Job } from "../types/api";

function RecentExperiments({ onOpen }: { onOpen: (id: string) => void }) {
  const { t } = useTranslation();
  const [jobs, setJobs] = useState<Job[] | null>(null);
  useEffect(() => {
    api
      .listJobs()
      .then((r) => setJobs(r.items.slice(0, 6)))
      .catch(() => setJobs([]));
  }, []);
  if (!jobs) return <div className="card p-5 text-center text-slate-400"><span className="spinner text-brand-500" /></div>;
  if (jobs.length === 0) {
    return (
      <div className="card p-5 text-sm text-slate-400">
        {t("home.noExperiments")}
      </div>
    );
  }
  return (
    <div className="card p-5">
      <h3 className="text-sm font-semibold text-slate-700 mb-3">{t("home.recent")}</h3>
      <ul className="divide-y divide-surface-border">
        {jobs.map((j) => (
          <li key={j.id}>
            <button
              className="w-full flex items-center gap-3 py-2.5 text-left hover:bg-surface-alt/50 rounded-md px-2 -mx-2 transition-colors"
              onClick={() => onOpen(j.id)}
            >
              <span className="font-mono text-[11px] text-slate-400 w-14 shrink-0">{j.model}</span>
              <span className="flex-1 min-w-0 truncate text-sm text-slate-700">{j.name || j.id}</span>
              {j.progress != null && j.status === "running" && (
                <span className="text-xs text-slate-400 w-10 text-right shrink-0">{j.progress}%</span>
              )}
              <StatusBadge status={j.status} />
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function HomePage({
  health,
  onOpenJob,
}: {
  health: HealthResponse | null;
  onOpenJob: (id: string) => void;
}) {
  const { t } = useTranslation();
  const [showManual, setShowManual] = useState(false);
  const backend: BackendInfo | null = health?.backend ?? null;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-800 tracking-tight">{t("home.centerTitle")}</h1>
          <p className="text-sm text-slate-500 mt-1">{t("home.centerSubtitle")}</p>
        </div>
        <div className="flex items-center gap-3">
          <BackendStatus info={backend} />
          <button className="btn-ghost" onClick={() => setShowManual((s) => !s)}>
            {showManual ? t("home.hideManual") : t("home.showManual")}
          </button>
        </div>
      </div>

      <div className="grid lg:grid-cols-[1fr_360px] gap-6 items-start">
        <AgentPanel onSubmitted={onOpenJob} />
        <div className="space-y-6">
          <RecentExperiments onOpen={onOpenJob} />
        </div>
      </div>

      {showManual && (
        <div>
          <ManualJobForm onCreated={onOpenJob} />
        </div>
      )}
    </div>
  );
}
