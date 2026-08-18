import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, ApiClientError } from "../api";
import { StatusBadge } from "../components/StatusBadge";
import { ProgressBar } from "../components/ProgressBar";
import { toast } from "../components/Toaster";
import type { Job, JobStatus } from "../types/api";

const POLL_MS = 3000;

export function JobsPage({ onOpen }: { onOpen: (id: string) => void }) {
  const { t } = useTranslation();
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [filter, setFilter] = useState<string>("all");
  const [error, setError] = useState<string | null>(null);
  // Track the last seen status of every job so we can fire a toast exactly once
  // when it transitions to a terminal state.
  const lastStatusRef = useRef<Map<string, JobStatus>>(new Map());
  const firstLoadRef = useRef(true);

  const load = useCallback(async () => {
    try {
      const res = await api.listJobs(filter === "all" ? undefined : filter);
      setJobs(res.items);
      setError(null);

      // Fire a toast when a job we saw in a previous poll moves to succeeded /
      // failed / canceled. We skip the very first load to avoid replaying
      // completions that happened before the page was opened.
      if (!firstLoadRef.current) {
        for (const job of res.items) {
          const prev = lastStatusRef.current.get(job.id);
          if (
            prev &&
            prev !== job.status &&
            (job.status === "succeeded" ||
              job.status === "failed" ||
              job.status === "canceled")
          ) {
            const label = job.name || job.id.slice(0, 8);
            if (job.status === "succeeded") {
              toast.success(t("jobs.toast.succeeded", { name: label }));
            } else if (job.status === "failed") {
              toast.error(t("jobs.toast.failed", { name: label }));
            } else {
              toast.info(t("jobs.toast.canceled", { name: label }));
            }
          }
          lastStatusRef.current.set(job.id, job.status);
        }
      } else {
        for (const job of res.items) {
          lastStatusRef.current.set(job.id, job.status);
        }
        firstLoadRef.current = false;
      }
    } catch (e) {
      setError(e instanceof ApiClientError ? e.body.message : String(e));
    }
  }, [filter, t]);

  useEffect(() => {
    firstLoadRef.current = true;
    lastStatusRef.current.clear();
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
  // Per-status counts derived from the current page's jobs.  Cheap and
  // good enough for the badge UX; the server-side total is also returned
  // in `total` if we ever want exact counts.
  const counts: Record<string, number> = { all: jobs?.length ?? 0 };
  for (const j of jobs ?? []) counts[j.status] = (counts[j.status] ?? 0) + 1;

  return (
    <div className="space-y-4 animate-fade-in-up">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-800">{t("jobs.title")}</h1>
        <div className="flex gap-1 flex-wrap">
          {filters.map((f) => {
            const active = filter === f;
            const count = counts[f] ?? 0;
            return (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                  active
                    ? "bg-brand-600 text-white shadow-sm"
                    : "bg-white border border-surface-border text-slate-600 hover:bg-surface-alt"
                }`}
              >
                <span>{f === "all" ? t("jobs.filterAll") : t(`jobs.status.${f}`)}</span>
                <span
                  className={`text-[10px] leading-none px-1.5 py-0.5 rounded-full ${
                    active
                      ? "bg-white/20 text-white"
                      : count > 0
                        ? "bg-slate-200 text-slate-600"
                        : "bg-slate-100 text-slate-400"
                  }`}
                >
                  {count}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-md px-3 py-2 flex items-center justify-between gap-2">
          <span className="flex-1">{error}</span>
          <button className="text-xs font-medium text-red-700 hover:text-red-800 underline shrink-0" onClick={() => void load()}>
            {t("common.retry")}
          </button>
        </div>
      )}

      {jobs === null ? (
        <div className="flex flex-col items-center justify-center py-10 gap-3">
        <div className="spinner text-brand-500" />
        <span className="text-sm text-slate-400">{t("common.loading")}</span>
      </div>
      ) : jobs.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 gap-3 text-center">
          <svg className="w-12 h-12 text-slate-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m4 4h10m-4-4v4m-5 4h.01M9 19h6" />
          </svg>
          <p className="text-slate-400 text-sm">
            {filter === "all" ? t("jobs.empty") : t("jobs.noJobs")}
          </p>
          {filter === "all" && (
            <a href="#/" className="text-brand-600 text-sm hover:underline">{t("home.title")}</a>
          )}
        </div>
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
                  <td className="px-4 py-3 text-slate-600 min-w-[140px]">
                    {job.status === "running" || job.status === "queued" ? (
                      <ProgressBar
                        progress={job.progress}
                        startedAt={job.started_at ?? job.created_at}
                        status={job.status}
                      />
                    ) : (
                      <span className="text-xs text-slate-400">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-slate-500 text-xs">{new Date(job.created_at).toLocaleString()}</td>
                  <td className="px-4 py-3 text-right whitespace-nowrap">
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
