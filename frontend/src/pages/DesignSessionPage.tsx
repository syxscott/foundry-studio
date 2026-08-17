/** DesignSessionPage: Main page for iterative protein design workflow.
 *
 * Two-panel layout (Rosetta/FoldX style):
 * - Left: Chat panel (conversation rounds, AI streaming, user input)
 * - Right: Candidates panel (all candidates, favorites, comparison)
 *
 * Features:
 * - AI response streaming via SSE
 * - Candidate cards with job submission
 * - Side-by-side candidate comparison
 * - Favorite management
 * - Continue to next round
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../api";
import { SessionProvider, useActiveSession, useSession } from "../components/SessionContext";
import { SessionList } from "../components/SessionList";
import { CandidateCard } from "../components/CandidateCard";
import { CandidateComparison } from "../components/CandidateComparison";
import { StructureViewer } from "../components/StructureViewer";
import { StatusBadge } from "../components/StatusBadge";
import { toast } from "../components/Toaster";
import type {
  CandidateFilter,
  DesignCandidate,
  DesignRound,
} from "../types/session";
import type { AgentPlan, JobStatus } from "../types/api";

interface DesignSessionPageProps {
  /** Session ID from URL params (null for new session) */
  sessionId: string | null;
}

/** Chat message component */
function ChatMessage({
  role,
  content,
  isStreaming,
}: {
  role: "user" | "assistant";
  content: string;
  isStreaming?: boolean;
}) {
  const { t } = useTranslation();

  if (role === "user") {
    return (
      <div className="flex gap-3">
        <div className="flex-shrink-0 w-8 h-8 rounded-full bg-brand-600 flex items-center justify-center">
          <svg
            className="w-4 h-4 text-white"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"
            />
          </svg>
        </div>
        <div className="flex-1 bg-slate-100 rounded-lg rounded-tl-none px-4 py-3">
          <p className="text-sm text-slate-700 whitespace-pre-wrap">{content}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex gap-3">
      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-accent-500 flex items-center justify-center">
        <svg
          className="w-4 h-4 text-white"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          aria-hidden="true"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
          />
        </svg>
      </div>
      <div className="flex-1 bg-brand-50 rounded-lg rounded-tl-none px-4 py-3">
        <div className="flex items-center gap-2 mb-1">
          <span className="text-xs font-medium text-brand-600">
            {t("designSession.round.aiThinking")}
          </span>
          {isStreaming && (
            <span className="flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-brand-500 animate-pulse" />
              <span className="text-xs text-brand-500">Streaming…</span>
            </span>
          )}
        </div>
        <p className="text-sm text-slate-700 whitespace-pre-wrap">{content}</p>
      </div>
    </div>
  );
}

/** Chat panel component */
function ChatPanel({
  onSendMessage,
  isStreaming,
  onCancel,
}: {
  onSendMessage: (message: string) => void;
  isStreaming: boolean;
  onCancel: () => void;
}) {
  const { t } = useTranslation();
  const [input, setInput] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const handleSubmit = () => {
    const message = input.trim();
    if (!message || isStreaming) return;
    onSendMessage(message);
    setInput("");
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  return (
    <div className="flex flex-col h-full">
      {/* Input area */}
      <div className="border-t border-surface-border p-3 bg-white">
        <div className="flex gap-2">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={t("designSession.placeholder")}
            className="flex-1 px-3 py-2 text-sm border border-surface-border rounded-lg resize-none focus:outline-none focus:ring-2 focus:ring-brand-500/30"
            rows={3}
            disabled={isStreaming}
          />
          <div className="flex flex-col gap-1">
            {isStreaming ? (
              <button
                onClick={onCancel}
                className="px-4 py-2 text-sm font-medium text-white bg-red-500 rounded-lg hover:bg-red-600 transition-colors"
              >
                {t("designSession.cancel")}
              </button>
            ) : (
              <button
                onClick={handleSubmit}
                disabled={!input.trim()}
                className="px-4 py-2 text-sm font-medium text-white bg-brand-600 rounded-lg hover:bg-brand-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {t("designSession.send")}
              </button>
            )}
          </div>
        </div>
        <p className="text-xs text-slate-400 mt-1">
          {t("designSession.inputHint")}
        </p>
      </div>
    </div>
  );
}

/** Candidates panel component */
function CandidatesPanel({
  filter,
  onFilterChange,
  selectedIds,
  onCompare,
  onOpen3D,
  compareMode,
  jobStatuses,
  onRunJob,
  onToggleFavorite,
  onContinue,
}: {
  filter: CandidateFilter;
  onFilterChange: (filter: CandidateFilter) => void;
  selectedIds: string[];
  onCompare: () => void;
  onOpen3D: (candidate: DesignCandidate) => void;
  compareMode: boolean;
  jobStatuses: Map<string, JobStatus>;
  onRunJob: (candidate: DesignCandidate) => void;
  onToggleFavorite: (candidateId: string) => void;
  onContinue: (candidate: DesignCandidate) => void;
}) {
  const { t } = useTranslation();
  const { session, getAllCandidates, getFavoriteCandidates } = useActiveSession();

  const allCandidates = session ? getAllCandidates(session.id) : [];
  const favoriteCandidates = session ? getFavoriteCandidates(session.id) : [];
  const currentRound = session?.rounds[session.rounds.length - 1];
  const thisRoundCandidates = currentRound?.candidates || [];

  const filteredCandidates =
    filter === "favorites"
      ? favoriteCandidates
      : filter === "thisRound"
        ? thisRoundCandidates
        : allCandidates;

  const tabs: { key: CandidateFilter; label: string; count: number }[] = [
    {
      key: "all",
      label: t("designSession.candidates.all"),
      count: allCandidates.length,
    },
    {
      key: "favorites",
      label: t("designSession.candidates.favorites"),
      count: favoriteCandidates.length,
    },
    {
      key: "thisRound",
      label: t("designSession.candidates.thisRound"),
      count: thisRoundCandidates.length,
    },
  ];

  return (
    <div className="flex flex-col h-full">
      {/* Filter tabs */}
      <div className="border-b border-surface-border px-3 pt-3">
        <div className="flex gap-1 mb-2">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => onFilterChange(tab.key)}
              className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
                filter === tab.key
                  ? "bg-brand-100 text-brand-700"
                  : "text-slate-600 hover:bg-slate-100"
              }`}
            >
              {tab.label}
              <span className="ml-1.5 text-xs opacity-70">({tab.count})</span>
            </button>
          ))}
        </div>
      </div>

      {/* Compare button */}
      <div className="px-3 py-2 border-b border-surface-border flex justify-end">
        <button
          onClick={onCompare}
          disabled={selectedIds.length === 0}
          className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
            compareMode
              ? "bg-brand-600 text-white"
              : "text-brand-600 bg-brand-50 hover:bg-brand-100"
          } disabled:opacity-50 disabled:cursor-not-allowed`}
        >
          {compareMode
            ? t("designSession.compare.exitCompare")
            : t("designSession.candidates.compare")}
        </button>
      </div>

      {/* Candidates grid */}
      <div className="flex-1 overflow-y-auto p-3">
        {filteredCandidates.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <svg
              className="w-12 h-12 text-slate-300 mb-3"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z"
              />
            </svg>
            <p className="text-sm text-slate-500">
              {t("designSession.candidates.empty")}
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-3">
            {filteredCandidates.map((candidate) => (
              <CandidateCard
                key={candidate.id}
                candidate={candidate}
                isFavorite={session?.favorites.includes(candidate.id) || false}
                isSelected={selectedIds.includes(candidate.id)}
                jobStatus={candidate.jobId ? jobStatuses.get(candidate.jobId) : undefined}
                onToggleFavorite={() => onToggleFavorite(candidate.id)}
                onRunJob={() => onRunJob(candidate)}
                onOpen3D={() => onOpen3D(candidate)}
                onCompare={() => {
                  if (selectedIds.includes(candidate.id)) {
                    // Deselect
                    onCompare(); // This will be handled by parent
                  } else if (selectedIds.length < 3) {
                    onCompare(); // This will be handled by parent
                  }
                }}
                onContinue={() => onContinue(candidate)}
                compareMode={compareMode}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/** Inner page content component (needs SessionProvider) */
function DesignSessionPageContent({ sessionId }: DesignSessionPageProps) {
  const { t, i18n } = useTranslation();
  const {
    session,
    currentRound,
    updateRound,
    addRound,
    addCandidate,
    updateCandidate,
    toggleFavorite,
  } = useActiveSession();
  const { createSession, setActiveSession, sessions } = useSession();

  const [filter, setFilter] = useState<CandidateFilter>("all");
  const [compareMode, setCompareMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [abortController, setAbortController] = useState<AbortController | null>(
    null,
  );
  const [jobStatuses, setJobStatuses] = useState<Map<string, JobStatus>>(
    new Map(),
  );
  const [structureUrl, setStructureUrl] = useState<string | null>(null);
  const [comparisonCandidates, setComparisonCandidates] = useState<
    DesignCandidate[]
  >([]);

  // Accumulator for streaming AI text — avoids functional updater mismatch.
  const aiMessageRef = useRef<{ roundId: string; text: string } | null>(null);

  // Sync active session with URL param. Use `sessions` (not memoized `session`)
  // as dependency so the effect fires reliably on URL changes.
  useEffect(() => {
    if (!sessionId) return;
    const existing = sessions.find((s) => s.id === sessionId);
    if (existing) {
      setActiveSession(sessionId);
    } else if (!session) {
      // Only create when neither a matching session exists NOR is one already active
      const newSession = createSession(t("designSession.newSessionDefault"));
      setActiveSession(newSession.id);
    }
  }, [sessions, sessionId, session, createSession, setActiveSession, t]);

  // Poll for job statuses
  useEffect(() => {
    if (!session) return;

    const pollInterval = setInterval(async () => {
      // Recompute inside the interval so we always poll the latest rounds.
      const candidateJobIds = session.rounds
        .flatMap((r) => r.candidates)
        .filter((c) => c.jobId)
        .map((c) => c.jobId!);

      if (candidateJobIds.length === 0) return;

      const newStatuses = new Map<string, JobStatus>();
      for (const jobId of candidateJobIds) {
        try {
          const job = await api.getJob(jobId);
          newStatuses.set(jobId, job.status);

          // Update candidate structure URL if job succeeded
          if (
            job.status === "succeeded" &&
            job.outputs.length > 0 &&
            !session.rounds
              .flatMap((r) => r.candidates)
              .find((c) => c.jobId === jobId)?.structureUrl
          ) {
            const structureOutput = job.outputs.find(
              (o) => o.kind === "structure" || o.name.endsWith(".cif"),
            );
            if (structureOutput) {
              // Find and update the candidate
              for (const round of session.rounds) {
                const candidate = round.candidates.find(
                  (c) => c.jobId === jobId,
                );
                if (candidate) {
                  updateCandidate(session.id, round.id, candidate.id, {
                    structureUrl: structureOutput.url,
                  });
                  break;
                }
              }
            }
          }
        } catch {
          // Job might not exist anymore
        }
      }
      setJobStatuses(newStatuses);
    }, 5000);

    return () => clearInterval(pollInterval);
  }, [session, updateCandidate]);

  /** Handle sending a message to the AI */
  const handleSendMessage = useCallback(
    (message: string) => {
      if (!session) return;

      const lang = i18n.language || "en";

      // Add user round
      const newRound = addRound(session.id, {
        userMessage: message,
        aiMessage: "",
        isStreaming: true,
        candidates: [],
        resolvedBy: "llm",
      });

      const roundId = newRound.id;
      aiMessageRef.current = { roundId, text: "" };

      setIsStreaming(true);
      const controller = new AbortController();
      setAbortController(controller);

      api.streamAgentChat(message, lang, {
        onToken: (text: string) => {
          const acc = aiMessageRef.current;
          if (!acc || acc.roundId !== roundId) return;
          acc.text += text;
          updateRound(session.id, roundId, { aiMessage: acc.text });
        },
        onPlan: (plan: AgentPlan) => {
          updateRound(session.id, roundId, {
            resolvedBy: plan.resolved_by as "llm" | "heuristic",
          });

          if (plan.name || plan.model) {
            const candidate = addCandidate(session.id, roundId, {
              name: plan.name || "Generated Candidate",
              sequence: "",
              description: `Generated using ${plan.model}`,
              annotations: {
                model: plan.model,
                resolvedBy: plan.resolved_by,
              },
            });

            updateCandidate(session.id, roundId, candidate.id, {
              annotations: {
                ...candidate.annotations,
                planParams: JSON.stringify(plan.params),
                planInvocation: JSON.stringify(plan.invocation),
              },
            });
          }
        },
        onDone: () => {
          setIsStreaming(false);
          setAbortController(null);
          aiMessageRef.current = null;
          updateRound(session.id, roundId, { isStreaming: false });
        },
        onError: (errorMsg: string) => {
          setIsStreaming(false);
          setAbortController(null);
          aiMessageRef.current = null;
          updateRound(session.id, roundId, { isStreaming: false });
          toast.error(t("designSession.error.aiError"), errorMsg);
        },
        signal: controller.signal,
      });
    },
    [session, addRound, updateRound, addCandidate, updateCandidate, i18n.language, t],
  );

  /** Cancel streaming */
  const handleCancel = useCallback(() => {
    abortController?.abort();
    setIsStreaming(false);
    setAbortController(null);
  }, [abortController]);

  /** Handle running a job for a candidate */
  const handleRunJob = useCallback(
    async (candidate: DesignCandidate) => {
      if (!session || !currentRound) return;

      try {
        const model = candidate.annotations?.model || "rfd3";
        const params =
          candidate.annotations?.planParams
            ? JSON.parse(candidate.annotations.planParams)
            : { contigs: candidate.sequence };

        // Create job
        const job = await api.createJob({
          model,
          name: candidate.name,
          params,
        });

        // Update candidate with job ID
        updateCandidate(session.id, currentRound.id, candidate.id, {
          jobId: job.id,
        });

        // Submit job
        await api.submitJob(job.id);

        toast.success(t("designSession.actions.submitJob"), job.name);
      } catch (e) {
        toast.error(
          t("designSession.error.submitFailed"),
          e instanceof Error ? e.message : String(e),
        );
      }
    },
    [session, currentRound, updateCandidate, t],
  );

  /** Handle toggling favorite */
  const handleToggleFavorite = useCallback(
    (candidateId: string) => {
      if (!session) return;
      toggleFavorite(session.id, candidateId);
    },
    [session, toggleFavorite],
  );

  /** Handle continue to next round */
  const handleContinue = useCallback(
    (candidate: DesignCandidate) => {
      if (!session) return;

      const message = `${t("designSession.continuePrompt")}: ${candidate.name} (${candidate.sequence.slice(0, 50)}...)`;
      // handleSendMessage calls addRound internally — no need to call it here too.
      void handleSendMessage(message);
    },
    [session, handleSendMessage, t],
  );

  /** Handle compare mode toggle */
  const handleCompare = useCallback(
    (candidateId?: string) => {
      if (!candidateId) {
        setCompareMode(!compareMode);
        if (!compareMode) {
          setSelectedIds([]);
        }
        return;
      }

      if (selectedIds.includes(candidateId)) {
        setSelectedIds(selectedIds.filter((id) => id !== candidateId));
      } else if (selectedIds.length < 3) {
        setSelectedIds([...selectedIds, candidateId]);
      } else {
        toast.warning(
          t("designSession.compare.maxReached"),
          t("designSession.compare.maxReachedDetail"),
        );
      }
    },
    [compareMode, selectedIds, t],
  );

  /** Handle opening 3D viewer */
  const handleOpen3D = useCallback((candidate: DesignCandidate) => {
    if (candidate.structureUrl) {
      setStructureUrl(candidate.structureUrl);
    }
  }, []);

  /** Handle opening comparison */
  const handleOpenComparison = useCallback(() => {
    if (!session) return;

    const allCandidates = session.rounds.flatMap((r) => r.candidates);
    const selected = allCandidates.filter((c) => selectedIds.includes(c.id));
    setComparisonCandidates(selected);
  }, [session, selectedIds]);

  // Open comparison when 2+ candidates selected
  useEffect(() => {
    if (compareMode && selectedIds.length >= 2) {
      handleOpenComparison();
    }
  }, [compareMode, selectedIds.length]);

  if (!session) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <p className="text-slate-500">{t("common.loading")}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full">
      {/* Left panel: Chat */}
      <div className="flex-1 flex flex-col border-r border-surface-border bg-white">
        {/* Session header */}
        <div className="px-4 py-3 border-b border-surface-border">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-semibold text-slate-800">
                {session.name}
              </h2>
              <p className="text-xs text-slate-500 mt-0.5">
                {t("designSession.roundCount", {
                  count: session.rounds.length,
                })}
              </p>
            </div>
          </div>
        </div>

        {/* Chat messages */}
        <div className="flex-1 overflow-y-auto p-4 space-y-6">
          {session.rounds.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-center">
              <svg
                className="w-16 h-16 text-slate-300 mb-4"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
                aria-hidden="true"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={1.5}
                  d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
                />
              </svg>
              <p className="text-slate-500 mb-2">
                {t("designSession.emptyChat")}
              </p>
              <p className="text-sm text-slate-400">
                {t("designSession.emptyChatHint")}
              </p>
            </div>
          ) : (
            <>
              {session.rounds.map((round: DesignRound) => (
                <div key={round.id} className="space-y-4">
                  <ChatMessage
                    role="user"
                    content={round.userMessage}
                  />
                  <ChatMessage
                    role="assistant"
                    content={round.aiMessage}
                    isStreaming={
                      round.isStreaming &&
                      round.id === currentRound?.id
                    }
                  />

                  {/* Candidates in this round */}
                  {round.candidates.length > 0 && (
                    <div className="ml-11 space-y-2">
                      <p className="text-xs font-medium text-slate-500">
                        {t("designSession.round.candidates", {
                          count: round.candidates.length,
                        })}
                      </p>
                      <div className="grid grid-cols-1 gap-2">
                        {round.candidates.map((candidate) => (
                          <div
                            key={candidate.id}
                            className="p-3 bg-slate-50 rounded-lg border border-surface-border"
                          >
                            <div className="flex items-center justify-between">
                              <div>
                                <span className="text-sm font-medium text-slate-700">
                                  {candidate.name}
                                </span>
                                {candidate.annotations?.model && (
                                  <span className="ml-2 text-xs text-slate-500">
                                    {candidate.annotations.model}
                                  </span>
                                )}
                              </div>
                              {candidate.jobId && (
                                <StatusBadge
                                  status={
                                    jobStatuses.get(candidate.jobId) || "draft"
                                  }
                                />
                              )}
                            </div>
                            {candidate.sequence && (
                              <code className="block mt-1 text-xs font-mono text-slate-600 overflow-hidden whitespace-nowrap text-ellipsis">
                                {candidate.sequence.slice(0, 60)}
                                {candidate.sequence.length > 60 && "…"}
                              </code>
                            )}
                            {candidate.description && (
                              <p className="mt-1 text-xs text-slate-500">
                                {candidate.description}
                              </p>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ))}
              <div ref={undefined} />
            </>
          )}
        </div>

        {/* Input area */}
        <ChatPanel
          onSendMessage={handleSendMessage}
          isStreaming={isStreaming}
          onCancel={handleCancel}
        />
      </div>

      {/* Right panel: Candidates */}
      <div className="w-96 flex flex-col bg-slate-50">
        <CandidatesPanel
          filter={filter}
          onFilterChange={setFilter}
          selectedIds={selectedIds}
          onCompare={() => handleCompare()}
          onOpen3D={handleOpen3D}
          compareMode={compareMode}
          jobStatuses={jobStatuses}
          onRunJob={handleRunJob}
          onToggleFavorite={handleToggleFavorite}
          onContinue={handleContinue}
        />
      </div>

      {/* 3D Structure Viewer Modal */}
      {structureUrl && (
        <StructureViewer
          url={structureUrl}
          onClose={() => setStructureUrl(null)}
        />
      )}

      {/* Candidate Comparison Modal */}
      {comparisonCandidates.length >= 2 && (
        <CandidateComparison
          candidates={comparisonCandidates}
          onClose={() => {
            setComparisonCandidates([]);
            setCompareMode(false);
            setSelectedIds([]);
          }}
          onContinue={handleContinue}
          jobStatuses={jobStatuses}
        />
      )}
    </div>
  );
}

/** Main exported component with SessionProvider wrapper */
export function DesignSessionPage({ sessionId }: DesignSessionPageProps) {
  return (
    <SessionProvider>
      <DesignSessionPageContent sessionId={sessionId} />
    </SessionProvider>
  );
}

/** Session wrapper that includes sidebar */
export function DesignSessionPageWithSidebar({
  sessionId,
}: DesignSessionPageProps) {
  return (
    <SessionProvider>
      <div className="flex h-full">
        {/* Sidebar */}
        <div className="w-64 flex-shrink-0 bg-white border-r border-surface-border">
          <SessionList />
        </div>

        {/* Main content */}
        <div className="flex-1">
          <DesignSessionPageContent sessionId={sessionId} />
        </div>
      </div>
    </SessionProvider>
  );
}

export default DesignSessionPage;
