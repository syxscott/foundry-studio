import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, ApiClientError } from "../api";
import { StatusBadge } from "../components/StatusBadge";
import type { Job, JobStatus } from "../types/api";

const POLL_MS = 3000;

export function JobsPage({ onOpen }: { onOpen: (id: string) => void }) {
  const { t } = useTranslation();
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [filter, setFilter] = useState<string>("all");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await api.listJobs(filter === "all" ? undefined : filter);
      setJobs(res.items);
      setError(null);
    } catch (e) {
      setError(e instanceof ApiClientError ? e.body.message : String(e));
    }
  }, [filter]);

  useEffect(() => {
    void load();
    const id = setInterval(() => void load(), POLL_MS);
    return () => clearInterval(id);
  }, [load]);

  const handleDelete = async (job: Job) => {
    if (!window.confirm(t("jobs.confirmDelete", { name: job.name }))) return;
    try {
      await api.deleteJob(job.id);
      void load();
    } catch (e) {
      window.alert(e instanceof ApiClientError ? e.body.message : String(e));
    }
  };

  const handleCancel = async (job: Job) => {
    if (!window.confirm(t("jobs.confirmCancel", { name: job.name }))) return;
    try {
      await api.cancelJob(job.id);
      void load();
    } catch (e) {
      window.alert(e instanceof ApiClientError ? e.body.message : String(e));
    }
  };

  const filters: (JobStatus | "all")[] = ["all", "queued", "running", "succeeded", "failed", "canceled"];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-800">{t("jobs.title")}</h1>
        <div className="flex gap-1 flex-wrap">
          {filters.map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                filter === f
                  ? "bg-brand-600 text-white shadow-sm"
                  : "bg-white border border-surface-border text-slate-600 hover:bg-surface-alt"
              }`}
            >
              {f === "all" ? t("jobs.filterAll") : t(`jobs.status.${f}`)}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-md px-3 py-2">{error}</div>
      )}

      {jobs === null ? (
        <p className="text-slate-400 py-10 text-center">{t("common.loading")}</p>
      ) : jobs.length === 0 ? (
        <p className="text-slate-400 py-10 text-center">
          {filter === "all" ? t("jobs.empty") : t("jobs.noJobs")}
        </p>
      ) : (
        <div className="card overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-surface-alt text-left text-xs uppercase tracking-wide text-slate-500">
                <th className="px-4 py-3 font-semibold">{t("jobs.col.name")}</th>
                <th className="px-4 py-3 font-semibold">{t("jobs.col.model")}</th>
                <th className="px-4 py-3 font-semibold">{t("jobs.col.status")}</th>
                <th className="px-4 py-3 font-semibold">{t("jobs.col.progress")}</th>
                <th className="px-4 py-3 font-semibold">{t("jobs.col.createdAt")}</th>
                <th className="px-4 py-3 text-right font-semibold">{t("jobs.col.actions")}</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => (
                <tr key={job.id} className="border-t border-surface-border hover:bg-surface-alt/70 transition-colors">
                  <td className="px-4 py-3">
                    <button className="text-brand-700 hover:underline font-medium" onClick={() => onOpen(job.id)}>
                      {job.name || job.id.slice(0, 8)}
                    </button>
                  </td>
                  <td className="px-4 py-3 text-slate-600 font-mono text-xs">{job.model}</td>
                  <td className="px-4 py-3"><StatusBadge status={job.status} /></td>
                  <td className="px-4 py-3 text-slate-600">
                    {job.status === "running" && job.progress != null ? `${job.progress}%` : "—"}
                  </td>
                  <td className="px-4 py-3 text-slate-500 text-xs">{new Date(job.created_at).toLocaleString()}</td>
                  <td className="px-4 py-3 text-right whitespace-nowrap">
                    <button className="text-brand-600 text-xs hover:underline mr-2" onClick={() => onOpen(job.id)}>
                      {t("jobs.view")}
                    </button>
                    {(job.status === "queued" || job.status === "running") && (
                      <button className="text-amber-600 text-xs hover:underline mr-2" onClick={() => void handleCancel(job)}>
                        {t("jobs.cancel")}
                      </button>
                    )}
                    {(job.status === "succeeded" || job.status === "failed" || job.status === "canceled") && (
                      <button className="text-red-500 text-xs hover:underline" onClick={() => void handleDelete(job)}>
                        {t("jobs.delete")}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
