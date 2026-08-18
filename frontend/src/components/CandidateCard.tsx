/** CandidateCard: Compact card displaying a design candidate.
 *
 * Shows:
 * - Name + model badge
 * - Sequence preview (truncated)
 * - Status badge (if job running)
 * - Favorite toggle (star)
 * - Actions: Run Job, Open 3D, Compare, Continue
 */

import { useState } from "react";
import { useTranslation } from "react-i18next";

import { StatusBadge } from "./StatusBadge";
import type { DesignCandidate } from "../types/session";
import type { JobStatus } from "../types/api";

interface CandidateCardProps {
  /** The candidate to display */
  candidate: DesignCandidate;
  /** Whether this candidate is favorited */
  isFavorite: boolean;
  /** Whether this candidate is selected in compare mode */
  isSelected: boolean;
  /** Job status if a job was submitted */
  jobStatus?: JobStatus;
  /** Job progress if running */
  jobProgress?: number | null;
  /** Callback when favorite is toggled */
  onToggleFavorite: () => void;
  /** Callback when "Run Job" is clicked */
  onRunJob?: () => void;
  /** Callback when "Open 3D" is clicked */
  onOpen3D?: () => void;
  /** Callback when "Compare" is clicked (toggle selection) */
  onCompare?: () => void;
  /** Callback when "Continue" is clicked (send to AI for next round) */
  onContinue?: () => void;
  /** Whether compare mode is enabled */
  compareMode?: boolean;
  /** Job name if a job was submitted */
  jobName?: string;
}

/** Truncate sequence for display */
function truncateSequence(sequence: string, maxLength: number = 60): string {
  if (sequence.length <= maxLength) return sequence;
  return `${sequence.slice(0, maxLength)}…`;
}

/** Calculate basic sequence metrics */
function calculateMetrics(sequence: string): {
  length: number;
  molecularWeight: string;
  isoelectricPoint: string;
} {
  const length = sequence.length;

  // Average amino acid molecular weights
  const aaWeights: Record<string, number> = {
    A: 89, R: 174, N: 132, D: 133, C: 121, E: 147, Q: 146, G: 75,
    H: 155, I: 131, L: 131, K: 146, M: 149, F: 165, P: 115, S: 105,
    T: 119, W: 204, Y: 181, V: 117,
  };

  let totalWeight = 0;
  for (const aa of sequence) {
    totalWeight += aaWeights[aa] || 110; // Default for unknown
  }

  // Simplified MW calculation
  const mw = (totalWeight - 18 * (length - 1)).toFixed(0);

  // Simplified pI estimation (very basic)
  const pI = "—"; // TODO: calculate from sequence composition

  return {
    length,
    molecularWeight: `${mw} Da`,
    isoelectricPoint: pI,
  };
}

export function CandidateCard({
  candidate,
  isFavorite,
  isSelected,
  jobStatus,
  jobProgress,
  onToggleFavorite,
  onRunJob,
  onOpen3D,
  onCompare,
  onContinue,
  compareMode = false,
}: CandidateCardProps) {
  const { t } = useTranslation();
  const [showDetails, setShowDetails] = useState(false);

  const hasStructure = !!candidate.structureUrl;
  const isJobRunning = jobStatus === "running" || jobStatus === "queued";
  const hasJob = !!candidate.jobId;

  const metrics = calculateMetrics(candidate.sequence);
  const modelBadge = candidate.annotations?.model || "RFD3";

  return (
    <div
      className={`relative rounded-lg border transition-all duration-200 ${
        isSelected
          ? "border-brand-500 bg-brand-50 shadow-md ring-2 ring-brand-500/30"
          : "border-surface-border bg-white hover:border-slate-300 hover:shadow-sm"
      }`}
    >
      {/* Selection indicator for compare mode */}
      {compareMode && (
        <div className="absolute top-2 left-2">
          <button
            onClick={onCompare}
            className={`w-5 h-5 rounded border-2 transition-colors flex items-center justify-center ${
              isSelected
                ? "bg-brand-600 border-brand-600 text-white"
                : "border-slate-300 bg-white hover:border-brand-400"
            }`}
            aria-label={t("designSession.candidate.selectForCompare")}
          >
            {isSelected && (
              <svg
                className="w-3 h-3"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
                aria-hidden="true"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={3}
                  d="M5 13l4 4L19 7"
                />
              </svg>
            )}
          </button>
        </div>
      )}

      {/* Favorite button */}
      <button
        onClick={(e) => {
          e.stopPropagation();
          onToggleFavorite();
        }}
        className={`absolute top-2 right-2 p-1.5 rounded-full transition-colors ${
          isFavorite
            ? "text-amber-500 bg-amber-50 hover:bg-amber-100"
            : "text-slate-300 hover:text-amber-500 hover:bg-slate-50"
        }`}
        title={
          isFavorite
            ? t("designSession.candidate.unfavorite")
            : t("designSession.candidate.favorite")
        }
      >
        <svg
          className="w-4 h-4"
          fill={isFavorite ? "currentColor" : "none"}
          stroke="currentColor"
          viewBox="0 0 24 24"
          aria-hidden="true"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z"
          />
        </svg>
      </button>

      <div className="p-3 pt-8">
        {/* Header: Name + Model badge */}
        <div className="flex items-center gap-2 mb-2">
          <h4 className="text-sm font-semibold text-slate-800 truncate flex-1">
            {candidate.name}
          </h4>
          <span className="px-1.5 py-0.5 text-[10px] font-medium bg-slate-100 text-slate-600 rounded">
            {modelBadge}
          </span>
        </div>

        {/* Job status */}
        {hasJob && jobStatus && (
          <div className="mb-2">
            <StatusBadge status={jobStatus} />
            {isJobRunning && jobProgress !== null && (
              <div className="mt-1 h-1 bg-slate-100 rounded-full overflow-hidden">
                <div
                  className="h-full bg-brand-500 transition-all duration-300"
                  style={{ width: `${jobProgress}%` }}
                />
              </div>
            )}
          </div>
        )}

        {/* Sequence preview */}
        <div className="mb-2">
          <p className="text-xs text-slate-500 mb-1">
            {t("designSession.candidate.sequence")}
          </p>
          <code className="block text-[11px] font-mono text-slate-700 bg-slate-50 px-2 py-1.5 rounded overflow-hidden whitespace-nowrap text-ellipsis">
            {truncateSequence(candidate.sequence)}
          </code>
        </div>

        {/* Basic metrics */}
        {showDetails && (
          <div className="mb-2 grid grid-cols-3 gap-1 text-[10px] text-slate-500">
            <div className="text-center">
              <span className="block font-medium text-slate-700">
                {metrics.length}
              </span>
              <span>{t("designSession.compare.metrics.length")}</span>
            </div>
            <div className="text-center">
              <span className="block font-medium text-slate-700">
                {metrics.molecularWeight}
              </span>
              <span>{t("designSession.compare.metrics.mw")}</span>
            </div>
            <div className="text-center">
              <span className="block font-medium text-slate-700">
                {metrics.isoelectricPoint}
              </span>
              <span>{t("designSession.compare.metrics.pI")}</span>
            </div>
          </div>
        )}

        {/* Description if present */}
        {candidate.description && (
          <p className="text-xs text-slate-600 mb-2 line-clamp-2">
            {candidate.description}
          </p>
        )}

        {/* Action buttons */}
        <div className="flex flex-wrap gap-1 mt-3">
          {/* Toggle details */}
          <button
            onClick={() => setShowDetails((s) => !s)}
            className="px-2 py-1 text-[10px] font-medium text-slate-600 bg-slate-100 rounded hover:bg-slate-200 transition-colors"
          >
            {showDetails ? t("designSession.candidate.hideDetails") : t("designSession.candidate.showDetails")}
          </button>

          {/* Run Job */}
          {!hasJob && onRunJob && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onRunJob();
              }}
              className="px-2 py-1 text-[10px] font-medium text-white bg-brand-600 rounded hover:bg-brand-700 transition-colors"
            >
              {t("designSession.candidate.runJob")}
            </button>
          )}

          {/* Open 3D */}
          {hasStructure && onOpen3D && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onOpen3D();
              }}
              className="px-2 py-1 text-[10px] font-medium text-slate-700 bg-slate-100 rounded hover:bg-slate-200 transition-colors flex items-center gap-1"
            >
              <svg
                className="w-3 h-3"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
                aria-hidden="true"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M14 10l-2 1m0 0l-2-1m2 1v2.5M20 7l-2 1m2-1l-2-1m2 1v2.5M14 4l-2-1-2 1M4 7l2-1M4 7l2 1M4 7v2.5M12 21l-2-1m2 1l2-1m-2 1v-2.5M6 18l-2-1v-2.5M18 18l2-1v-2.5"
                />
              </svg>
              {t("designSession.candidate.open3d")}
            </button>
          )}

          {/* Compare (only in compare mode) */}
          {compareMode && onCompare && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onCompare();
              }}
              className={`px-2 py-1 text-[10px] font-medium rounded transition-colors ${
                isSelected
                  ? "text-brand-700 bg-brand-100 hover:bg-brand-200"
                  : "text-slate-600 bg-slate-100 hover:bg-slate-200"
              }`}
            >
              {t("designSession.candidate.compare")}
            </button>
          )}

          {/* Continue to next round */}
          {onContinue && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                onContinue();
              }}
              className="px-2 py-1 text-[10px] font-medium text-accent-600 bg-accent-50 rounded hover:bg-accent-100 transition-colors flex items-center gap-1"
            >
              <svg
                className="w-3 h-3"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
                aria-hidden="true"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M13 7l5 5m0 0l-5 5m5-5H6"
                />
              </svg>
              {t("designSession.candidate.continue")}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export default CandidateCard;
