/** Animated progress bar with ETA.

Reads `progress` (0..100) and `startedAt` (ISO) and:
- renders an animated indeterminate bar when `progress == null`,
- renders a determinate bar with percentage otherwise,
- computes ETA from elapsed time + progress when `progress > 0 && progress < 100`,
- falls back to a neutral "queued" bar when the job has not started yet.
*/

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

function formatDuration(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "—";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  if (m < 60) return `${m}m ${s.toString().padStart(2, "0")}s`;
  const h = Math.floor(m / 60);
  return `${h}h ${(m % 60).toString().padStart(2, "0")}m`;
}

export function ProgressBar({
  progress,
  startedAt,
  status,
}: {
  progress: number | null | undefined;
  startedAt?: string | null;
  status: string;
}) {
  const { t } = useTranslation();

  // Tick once a second while the job is running so the ETA and elapsed labels
  // update without depending on the parent's polling cycle.
  const [now, setNow] = useState<number>(() => Date.now());
  useEffect(() => {
    if (status !== "running" && status !== "queued") return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [status]);

  if (status === "queued" || (status === "running" && progress == null)) {
    return (
      <div className="space-y-1">
        <div className="flex items-center gap-1.5 text-xs text-slate-500">
          <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse" />
          <span>{t(`jobs.status.${status}` as never)}</span>
        </div>
        <div className="h-1.5 rounded-full bg-slate-100 overflow-hidden">
          <div className="h-full w-1/3 bg-blue-400 rounded-full animate-indeterminate" />
        </div>
      </div>
    );
  }

  if (status === "succeeded") {
    return (
      <div className="space-y-1">
        <div className="flex items-center gap-1.5 text-xs text-emerald-700">
          <span>{t("jobDetail.completed")}</span>
        </div>
        <div className="h-1.5 rounded-full bg-emerald-100 overflow-hidden">
          <div className="h-full w-full bg-emerald-500 rounded-full" />
        </div>
      </div>
    );
  }

  if (status === "failed" || status === "canceled") {
    return (
      <div className="space-y-1">
        <div className="flex items-center gap-1.5 text-xs text-slate-500">
          <span>{t(`jobs.status.${status}` as never)}</span>
          {progress !== null && progress !== undefined && (
            <span className="text-slate-400">({Math.round(progress)}%)</span>
          )}
        </div>
        <div className="h-1.5 rounded-full bg-slate-100 overflow-hidden">
          <div
            className={`h-full rounded-full ${status === "failed" ? "bg-red-400" : "bg-slate-400"}`}
            style={{ width: "100%" }}
          />
        </div>
      </div>
    );
  }

  // Running with progress
  const pct = Math.max(0, Math.min(100, progress ?? 0));
  const startMs = startedAt ? new Date(startedAt).getTime() : null;
  const elapsedSec = startMs ? Math.max(0, (now - startMs) / 1000) : 0;
  const eta =
    startMs && pct > 1 && pct < 100 && elapsedSec > 30
      ? formatDuration(Math.min((elapsedSec * (100 - pct)) / pct, 7200)) // cap at 2h
      : null;
  const elapsed = startMs ? formatDuration(elapsedSec) : null;

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs text-slate-500">
        <div className="flex items-center gap-2">
          <span className="font-mono text-slate-700">{Math.round(pct)}%</span>
          {elapsed && <span>{t("common.elapsed")} {elapsed}</span>}
        </div>
        {eta && <span>{t("common.eta")} {eta}</span>}
      </div>
      <div
        className="h-1.5 rounded-full bg-slate-100 overflow-hidden"
        role="progressbar"
        aria-valuenow={Math.round(pct)}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div
          className="h-full bg-gradient-to-r from-brand-500 to-accent-500 rounded-full transition-[width] duration-700 ease-out"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
