import { useTranslation } from "react-i18next";
import type { JobStatus } from "../types/api";

const STATUS_STYLES: Record<JobStatus, { box: string; dot: string }> = {
  draft: { box: "bg-slate-100 text-slate-600 border-slate-200", dot: "bg-slate-400" },
  queued: { box: "bg-blue-50 text-blue-700 border-blue-200", dot: "bg-blue-500" },
  running: { box: "bg-indigo-50 text-indigo-700 border-indigo-200", dot: "bg-indigo-500" },
  succeeded: { box: "bg-green-50 text-green-700 border-green-200", dot: "bg-green-500" },
  failed: { box: "bg-red-50 text-red-700 border-red-200", dot: "bg-red-500" },
  canceled: { box: "bg-slate-100 text-slate-500 border-slate-200", dot: "bg-slate-400" },
};

export function StatusBadge({ status }: { status: JobStatus }) {
  const { t } = useTranslation();
  const s = STATUS_STYLES[status] ?? STATUS_STYLES.draft;
  return (
    <span className={`badge ${s.box}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${s.dot}`} />
      {t(`jobs.status.${status}`)}
    </span>
  );
}
