import { useTranslation } from "react-i18next";
import type { JobStatus } from "../types/api";

const STATUS_STYLES: Record<JobStatus, string> = {
  draft: "bg-slate-100 text-slate-600 border-slate-200",
  queued: "bg-blue-50 text-blue-700 border-blue-200",
  running: "bg-indigo-50 text-indigo-700 border-indigo-200",
  succeeded: "bg-green-50 text-green-700 border-green-200",
  failed: "bg-red-50 text-red-700 border-red-200",
  canceled: "bg-slate-100 text-slate-500 border-slate-200",
};

export function StatusBadge({ status }: { status: JobStatus }) {
  const { t } = useTranslation();
  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${STATUS_STYLES[status] ?? STATUS_STYLES.draft}`}
    >
      {t(`jobs.status.${status}`)}
    </span>
  );
}
