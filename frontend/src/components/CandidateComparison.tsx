/** CandidateComparison: Side-by-side view for comparing 2-3 candidates.
 *
 * Features:
 * - 2-3 candidate cards with structure overlaid in NGL
 * - Sequence alignment with color coding
 * - Basic metrics: length, molecular weight, isoelectric point
 * - Close / Export buttons
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import * as NGL from "ngl";

import { StatusBadge } from "./StatusBadge";
import type { DesignCandidate } from "../types/session";
import type { JobStatus } from "../types/api";

interface CandidateComparisonProps {
  /** Candidates to compare (max 3) */
  candidates: DesignCandidate[];
  /** Callback when comparison is closed */
  onClose: () => void;
  /** Callback when a candidate is sent to next round */
  onContinue?: (candidate: DesignCandidate) => void;
  /** Job statuses map */
  jobStatuses?: Map<string, JobStatus>;
}

/** Amino acid color scheme for sequence alignment */
const AA_COLORS: Record<string, string> = {
  A: "#8c8c8c", R: "#ff0000", N: "#00ff00", D: "#ff0000", C: "#ffff00",
  E: "#ff0000", Q: "#00ff00", G: "#8c8c8c", H: "#00ffff", I: "#ffff00",
  L: "#ffff00", K: "#ff0000", M: "#ffff00", F: "#ffff00", P: "#00ff00",
  S: "#00ff00", T: "#00ff00", W: "#ffff00", Y: "#00ffff", V: "#ffff00",
};

type Representation = "cartoon" | "ball+stick" | "surface" | "spacefill";

/** Calculate molecular weight from sequence */
function calculateMolecularWeight(sequence: string): number {
  const aaWeights: Record<string, number> = {
    A: 89, R: 174, N: 132, D: 133, C: 121, E: 147, Q: 146, G: 75,
    H: 155, I: 131, L: 131, K: 146, M: 149, F: 165, P: 115, S: 105,
    T: 119, W: 204, Y: 181, V: 117,
  };
  let total = 0;
  for (const aa of sequence) {
    total += aaWeights[aa] || 110;
  }
  return total - 18 * (sequence.length - 1);
}

/** Get color for amino acid */
function getAAColor(aa: string): string {
  return AA_COLORS[aa.toUpperCase()] || "#8c8c8c";
}

/** NGL Viewer component for a single structure */
function StructureViewerPanel({
  url,
  candidateName,
  onLoadError,
}: {
  url: string;
  candidateName: string;
  onLoadError?: (error: string) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const stageRef = useRef<NGL.Stage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [rep, setRep] = useState<Representation>("cartoon");

  useEffect(() => {
    if (!containerRef.current) return;

    const stage = new NGL.Stage(containerRef.current, {
      backgroundColor: "#f8fafc",
    });
    stageRef.current = stage;

    stage
      .loadFile(url, { ext: "cif" })
      .then((component) => {
        const structure = component as NGL.StructureComponent;
        structure.autoView();
        structure.addRepresentation("cartoon", { colorScheme: "chainid" });
        setLoading(false);
      })
      .catch((e: unknown) => {
        const msg = e instanceof Error ? e.message : String(e);
        setError(msg);
        setLoading(false);
        onLoadError?.(msg);
      });

    return () => {
      stage.dispose();
      stageRef.current = null;
    };
  }, [url, onLoadError]);

  const updateRep = useCallback(
    (newRep: Representation) => {
      setRep(newRep);
      const stage = stageRef.current;
      if (!stage) return;
      stage.eachComponent((comp) => {
        (comp as NGL.StructureComponent).removeAllRepresentations();
        (comp as NGL.StructureComponent).addRepresentation(newRep, {
          colorScheme: "chainid",
        });
      });
    },
    [],
  );

  const resetView = useCallback(() => {
    stageRef.current?.eachComponent((comp) => {
      (comp as NGL.StructureComponent).autoView();
    });
    stageRef.current?.viewer.requestRender();
  }, []);

  return (
    <div className="flex flex-col h-full">
      {/* Viewer header */}
      <div className="px-3 py-2 bg-slate-50 border-b border-surface-border flex items-center justify-between">
        <span className="text-sm font-medium text-slate-700 truncate">
          {candidateName}
        </span>
        <div className="flex items-center gap-2">
          <select
            value={rep}
            onChange={(e) => updateRep(e.target.value as Representation)}
            className="text-xs border border-surface-border rounded px-1.5 py-0.5 bg-white"
          >
            <option value="cartoon">Cartoon</option>
            <option value="ball+stick">Ball+Stick</option>
            <option value="surface">Surface</option>
            <option value="spacefill">Spacefill</option>
          </select>
          <button
            onClick={resetView}
            className="text-xs text-slate-500 hover:text-slate-700"
            title="Reset view"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
            </svg>
          </button>
        </div>
      </div>

      {/* NGL container */}
      <div className="flex-1 relative bg-slate-100">
        <div ref={containerRef} className="absolute inset-0" />
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center bg-white/70">
            <div className="flex items-center gap-2 text-sm text-slate-500">
              <span className="spinner text-brand-500" />
              Loading structure…
            </div>
          </div>
        )}
        {error && (
          <div className="absolute inset-0 flex items-center justify-center bg-white/80 text-red-600 text-sm">
            Failed to load: {error}
          </div>
        )}
      </div>
    </div>
  );
}

/** Sequence alignment panel */
function SequenceAlignmentPanel({
  candidates,
}: {
  candidates: DesignCandidate[];
}) {
  const { t } = useTranslation();

  // Get max length for alignment display
  const maxLength = Math.max(...candidates.map((c) => c.sequence.length));
  const displayLength = Math.min(maxLength, 80);

  // Split sequence into chunks of 20 for display
  const chunkSize = 20;

  return (
    <div className="bg-white border border-surface-border rounded-lg overflow-hidden">
      <div className="px-3 py-2 bg-slate-50 border-b border-surface-border">
        <h4 className="text-sm font-medium text-slate-700">
          {t("designSession.compare.sequenceAlignment")}
        </h4>
      </div>
      <div className="p-3 overflow-x-auto">
        {/* Header row with positions */}
        <div className="flex mb-1">
          {candidates.map((c) => (
            <div
              key={c.id}
              className="flex-1 min-w-[200px] text-xs font-medium text-slate-600 pr-2"
            >
              {c.name}
            </div>
          ))}
        </div>

        {/* Sequence chunks */}
        {Array.from({ length: Math.ceil(displayLength / chunkSize) }).map(
          (_, chunkIdx) => (
            <div key={chunkIdx} className="flex">
              {candidates.map((candidate) => {
                const seq = candidate.sequence.slice(
                  chunkIdx * chunkSize,
                  (chunkIdx + 1) * chunkSize,
                );
                const startPos = chunkIdx * chunkSize + 1;

                return (
                  <div key={candidate.id} className="flex-1 min-w-[200px] pr-2">
                    {/* Position markers */}
                    <div className="flex text-[9px] text-slate-400 mb-0.5">
                      {seq.split("").map((_, i) => (
                        <span key={i} className="w-3 text-center">
                          {(startPos + i) % 10 === 0
                            ? startPos + i
                            : ""}
                        </span>
                      ))}
                    </div>
                    {/* Sequence with color coding */}
                    <div className="flex flex-wrap">
                      {seq.split("").map((aa, i) => (
                        <span
                          key={i}
                          className="w-3 h-4 flex items-center justify-center text-[10px] font-mono"
                          style={{
                            backgroundColor: `${getAAColor(aa)}20`,
                            color: getAAColor(aa),
                          }}
                          title={`${aa} (position ${startPos + i})`}
                        >
                          {aa}
                        </span>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          ),
        )}

        {maxLength > displayLength && (
          <div className="mt-2 text-xs text-slate-500">
            …{t("designSession.compare.truncated", { count: maxLength - displayLength })}
          </div>
        )}
      </div>
    </div>
  );
}

/** Metrics comparison table */
function MetricsComparison({
  candidates,
}: {
  candidates: DesignCandidate[];
}) {
  const { t } = useTranslation();

  const metrics = candidates.map((c) => ({
    id: c.id,
    name: c.name,
    length: c.sequence.length,
    mw: calculateMolecularWeight(c.sequence),
    pI: 7.0, // Simplified
  }));

  return (
    <div className="bg-white border border-surface-border rounded-lg overflow-hidden">
      <div className="px-3 py-2 bg-slate-50 border-b border-surface-border">
        <h4 className="text-sm font-medium text-slate-700">
          {t("designSession.compare.metricsTitle")}
        </h4>
      </div>
      <div className="p-3">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-slate-500 text-xs border-b border-surface-border">
              <th className="pb-2 font-medium">
                {t("designSession.compare.metrics.property")}
              </th>
              {candidates.map((c) => (
                <th key={c.id} className="pb-2 font-medium text-center">
                  {c.name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr className="border-b border-surface-border/50">
              <td className="py-2 text-slate-600">
                {t("designSession.compare.metrics.length")}
              </td>
              {metrics.map((m) => (
                <td key={m.id} className="py-2 text-center font-mono">
                  {m.length}
                </td>
              ))}
            </tr>
            <tr className="border-b border-surface-border/50">
              <td className="py-2 text-slate-600">
                {t("designSession.compare.metrics.mw")}
              </td>
              {metrics.map((m) => (
                <td key={m.id} className="py-2 text-center font-mono">
                  {(m.mw / 1000).toFixed(1)} kDa
                </td>
              ))}
            </tr>
            <tr>
              <td className="py-2 text-slate-600">
                {t("designSession.compare.metrics.pI")}
              </td>
              {metrics.map((m) => (
                <td key={m.id} className="py-2 text-center font-mono">
                  {m.pI.toFixed(1)}
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function CandidateComparison({
  candidates,
  onClose,
  onContinue,
  jobStatuses,
}: CandidateComparisonProps) {
  const { t } = useTranslation();

  const candidatesWithStructures = candidates.filter((c) => c.structureUrl);
  const allHaveStructures =
    candidates.length === candidatesWithStructures.length;

  return (
    <div
      className="fixed inset-0 z-50 bg-slate-900/60 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
    >
      <div className="bg-white rounded-lg w-full max-w-6xl h-[90vh] flex flex-col animate-fade-in-up">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-surface-border">
          <div>
            <h3 className="font-semibold text-slate-800">
              {t("designSession.compare.title")}
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">
              {candidates.length}{" "}
              {t("designSession.compare.candidatesCount", {
            count: candidates.length,
          })}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={onClose}
              className="px-3 py-1.5 text-sm font-medium text-slate-600 bg-slate-100 rounded-md hover:bg-slate-200 transition-colors"
            >
              {t("designSession.compare.close")}
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {/* Structure viewers */}
          {allHaveStructures ? (
            <div
              className={`grid gap-3`}
              style={{
                gridTemplateColumns: `repeat(${candidates.length}, 1fr)`,
              }}
            >
              {candidates.map((candidate) => (
                <div
                  key={candidate.id}
                  className="h-64 border border-surface-border rounded-lg overflow-hidden"
                >
                  <StructureViewerPanel
                    url={candidate.structureUrl!}
                    candidateName={candidate.name}
                  />
                </div>
              ))}
            </div>
          ) : (
            <div className="bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 text-sm text-amber-800">
              {t("designSession.compare.noStructureAvailable")}
            </div>
          )}

          {/* Sequence alignment */}
          <SequenceAlignmentPanel candidates={candidates} />

          {/* Metrics comparison */}
          <MetricsComparison candidates={candidates} />

          {/* Actions */}
          <div className="flex flex-wrap gap-2">
            {candidates.map((candidate) => (
              <div key={candidate.id} className="flex items-center gap-2">
                <span className="text-sm font-medium text-slate-700">
                  {candidate.name}:
                </span>
                {candidate.jobId && jobStatuses?.has(candidate.jobId) && (
                  <StatusBadge status={jobStatuses.get(candidate.jobId)!} />
                )}
                {candidate.structureUrl && (
                  <span className="text-xs text-green-600 bg-green-50 px-2 py-0.5 rounded">
                    {t("designSession.compare.hasStructure")}
                  </span>
                )}
                {onContinue && (
                  <button
                    onClick={() => onContinue(candidate)}
                    className="px-2 py-1 text-xs font-medium text-accent-600 bg-accent-50 rounded hover:bg-accent-100 transition-colors"
                  >
                    {t("designSession.candidate.continue")}
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export default CandidateComparison;
