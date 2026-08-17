/** SessionList: Sidebar component showing all design sessions.
 *
 * Features:
 * - List all sessions with name, last updated, round count
 * - Active session indicator
 * - Create new session button
 * - Delete session button
 * - Click to switch session
 */

import { useState } from "react";
import { useTranslation } from "react-i18next";

import { useSession } from "./SessionContext";

interface SessionListProps {
  /** Callback when user wants to navigate to design page */
  onNavigate?: () => void;
}

/** Format relative time (e.g., "2 min ago", "yesterday") */
function formatRelativeTime(
  timestamp: number,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  t: (key: string, opts?: any) => string,
): string {
  const now = Date.now();
  const diff = now - timestamp;
  const seconds = Math.floor(diff / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);

  if (seconds < 60) return t("designSession.time.justNow");
  if (minutes < 60) return t("designSession.time.minutesAgo", { count: String(minutes) });
  if (hours < 24) return t("designSession.time.hoursAgo", { count: String(hours) });
  if (days === 1) return t("designSession.time.yesterday");
  if (days < 7) return t("designSession.time.daysAgo", { count: String(days) });

  return new Date(timestamp).toLocaleDateString();
}

export function SessionList({ onNavigate }: SessionListProps) {
  const { t } = useTranslation();
  const {
    sessions,
    activeSession,
    createSession,
    deleteSession,
    setActiveSession,
  } = useSession();

  const [isCreating, setIsCreating] = useState(false);
  const [newSessionName, setNewSessionName] = useState("");
  const [deletingId, setDeletingId] = useState<string | null>(null);

  /** Handle creating a new session */
  const handleCreate = () => {
    const name = newSessionName.trim() || t("designSession.newSessionDefault");
    const session = createSession(name);
    setNewSessionName("");
    setIsCreating(false);
    onNavigate?.();
    void session;
  };

  /** Handle creating with Enter key */
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      handleCreate();
    } else if (e.key === "Escape") {
      setIsCreating(false);
      setNewSessionName("");
    }
  };

  /** Handle session click */
  const handleSessionClick = (sessionId: string) => {
    setActiveSession(sessionId);
    onNavigate?.();
  };

  /** Handle delete with confirmation */
  const handleDelete = (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation();
    if (deletingId === sessionId) {
      deleteSession(sessionId);
      setDeletingId(null);
    } else {
      setDeletingId(sessionId);
      // Reset after 3 seconds if not confirmed
      setTimeout(() => setDeletingId((current) => (current === sessionId ? null : current)), 3000);
    }
  };

  /** Sort sessions by updatedAt descending */
  const sortedSessions = [...sessions].sort(
    (a, b) => b.updatedAt - a.updatedAt,
  );

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-3 py-2 border-b border-surface-border">
        <h2 className="text-sm font-semibold text-slate-700">
          {t("designSession.sidebar.title")}
        </h2>
      </div>

      {/* Create new session */}
      <div className="px-3 py-2 border-b border-surface-border">
        {isCreating ? (
          <div className="space-y-2">
            <input
              type="text"
              value={newSessionName}
              onChange={(e) => setNewSessionName(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={t("designSession.newSessionPlaceholder")}
              className="w-full px-2 py-1.5 text-sm border border-surface-border rounded-md focus:outline-none focus:ring-2 focus:ring-brand-500/30"
              autoFocus
            />
            <div className="flex gap-1">
              <button
                onClick={handleCreate}
                className="flex-1 px-2 py-1 text-xs font-medium text-white bg-brand-600 rounded hover:bg-brand-700 transition-colors"
              >
                {t("designSession.create")}
              </button>
              <button
                onClick={() => {
                  setIsCreating(false);
                  setNewSessionName("");
                }}
                className="px-2 py-1 text-xs font-medium text-slate-600 bg-slate-100 rounded hover:bg-slate-200 transition-colors"
              >
                {t("common.cancel")}
              </button>
            </div>
          </div>
        ) : (
          <button
            onClick={() => setIsCreating(true)}
            className="w-full flex items-center justify-center gap-1.5 px-3 py-2 text-sm font-medium text-brand-600 bg-brand-50 rounded-md hover:bg-brand-100 transition-colors"
          >
            <svg
              className="w-4 h-4"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 4v16m8-8H4"
              />
            </svg>
            {t("designSession.newSession")}
          </button>
        )}
      </div>

      {/* Session list */}
      <div className="flex-1 overflow-y-auto">
        {sortedSessions.length === 0 ? (
          <div className="px-3 py-8 text-center text-sm text-slate-500">
            {t("designSession.sidebar.empty")}
          </div>
        ) : (
          <ul className="py-1">
            {sortedSessions.map((session) => {
              const isActive = activeSession?.id === session.id;
              const isDeleting = deletingId === session.id;
              const roundCount = session.rounds.length;
              const candidateCount = session.rounds.reduce(
                (acc, r) => acc + r.candidates.length,
                0,
              );

              return (
                <li key={session.id}>
                  <button
                    onClick={() => handleSessionClick(session.id)}
                    className={`w-full px-3 py-2.5 text-left transition-colors group ${
                      isActive
                        ? "bg-brand-50 border-l-2 border-brand-600"
                        : "hover:bg-slate-50 border-l-2 border-transparent"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex-1 min-w-0">
                        <p
                          className={`text-sm font-medium truncate ${
                            isActive ? "text-brand-700" : "text-slate-700"
                          }`}
                        >
                          {session.name}
                        </p>
                        <p className="text-xs text-slate-500 mt-0.5">
                          {t("designSession.sidebar.rounds", {
                            count: roundCount,
                          })}{" "}
                          ·{" "}
                          {t("designSession.sidebar.candidates", {
                            count: candidateCount,
                          })}
                        </p>
                        <p className="text-xs text-slate-400 mt-0.5">
                          {formatRelativeTime(session.updatedAt, t)}
                        </p>
                      </div>

                      {/* Delete button */}
                      <button
                        onClick={(e) => handleDelete(e, session.id)}
                        className={`p-1 rounded transition-colors ${
                          isDeleting
                            ? "bg-red-100 text-red-600"
                            : "text-slate-400 opacity-0 group-hover:opacity-100 hover:text-red-500 hover:bg-red-50"
                        }`}
                        title={
                          isDeleting
                            ? t("designSession.confirmDelete")
                            : t("designSession.delete")
                        }
                      >
                        <svg
                          className="w-3.5 h-3.5"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                          aria-hidden="true"
                        >
                          {isDeleting ? (
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth={2}
                              d="M6 18L18 6M6 6l12 12"
                            />
                          ) : (
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth={2}
                              d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                            />
                          )}
                        </svg>
                      </button>
                    </div>

                    {/* Active indicator dot */}
                    {isActive && (
                      <div className="flex items-center gap-1.5 mt-1.5">
                        <span className="w-1.5 h-1.5 rounded-full bg-brand-500" />
                        <span className="text-xs text-brand-600 font-medium">
                          {t("designSession.sidebar.active")}
                        </span>
                      </div>
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {/* Footer with session count */}
      <div className="px-3 py-2 border-t border-surface-border text-xs text-slate-400">
        {t("designSession.sidebar.total", { count: sessions.length })}
      </div>
    </div>
  );
}

export default SessionList;
