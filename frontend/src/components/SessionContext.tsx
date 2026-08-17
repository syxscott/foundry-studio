/** SessionContext: React context providing Design Session state management.
 *
 * All state lives in React state (no backend persistence for MVP).
 * Provides CRUD operations for sessions, rounds, candidates, and favorites.
 */

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
} from "react";

import type {
  DesignCandidate,
  DesignRound,
  DesignSession,
} from "../types/session";

/** Generate a unique ID using crypto.randomUUID */
function generateId(): string {
  return crypto.randomUUID();
}

/** Context shape definition */
interface SessionContextValue {
  /** All sessions */
  sessions: DesignSession[];
  /** Currently active session (null if none selected) */
  activeSession: DesignSession | null;
  /** Create a new session with the given name */
  createSession: (name: string) => DesignSession;
  /** Update an existing session */
  updateSession: (id: string, updates: Partial<DesignSession>) => void;
  /** Delete a session by ID */
  deleteSession: (id: string) => void;
  /** Set the active session by ID (null to deselect) */
  setActiveSession: (id: string | null) => void;
  /** Add a new round to a session */
  addRound: (sessionId: string, round: Omit<DesignRound, "id">) => DesignRound;
  /** Update an existing round */
  updateRound: (
    sessionId: string,
    roundId: string,
    updates: Partial<DesignRound>,
  ) => void;
  /** Add a candidate to a session's round */
  addCandidate: (
    sessionId: string,
    roundId: string,
    candidate: Omit<DesignCandidate, "id" | "roundId" | "createdAt">,
  ) => DesignCandidate;
  /** Update an existing candidate */
  updateCandidate: (
    sessionId: string,
    roundId: string,
    candidateId: string,
    updates: Partial<DesignCandidate>,
  ) => void;
  /** Toggle favorite status for a candidate */
  toggleFavorite: (sessionId: string, candidateId: string) => void;
  /** Get all candidates across all rounds in a session */
  getAllCandidates: (sessionId: string) => DesignCandidate[];
  /** Get candidates for a specific round */
  getRoundCandidates: (
    sessionId: string,
    roundId: string,
  ) => DesignCandidate[];
  /** Get favorite candidates for a session */
  getFavoriteCandidates: (sessionId: string) => DesignCandidate[];
  /** Find which round a candidate belongs to */
  findCandidateRound: (
    sessionId: string,
    candidateId: string,
  ) => DesignRound | undefined;
}

/** Create empty session template */
function createEmptySession(name: string): DesignSession {
  const now = Date.now();
  return {
    id: generateId(),
    name,
    createdAt: now,
    updatedAt: now,
    rounds: [],
    favorites: [],
    status: "active",
  };
}

/** Create empty round template */
function createEmptyRound(
  userMessage: string,
): Omit<DesignRound, "id"> {
  return {
    userMessage,
    aiMessage: "",
    isStreaming: true,
    candidates: [],
    resolvedBy: "llm",
  };
}

/** Create candidate template */
function createCandidate(
  roundId: string,
  data: Omit<DesignCandidate, "id" | "roundId" | "createdAt">,
): DesignCandidate {
  return {
    ...data,
    id: generateId(),
    roundId,
    createdAt: Date.now(),
  };
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [sessions, setSessions] = useState<DesignSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);

  /** Active session derived from sessions state */
  const activeSession = useMemo(
    () => sessions.find((s) => s.id === activeSessionId) ?? null,
    [sessions, activeSessionId],
  );

  /** Create a new session */
  const createSession = useCallback((name: string): DesignSession => {
    const newSession = createEmptySession(name);
    setSessions((prev) => [...prev, newSession]);
    setActiveSessionId(newSession.id);
    return newSession;
  }, []);

  /** Update an existing session */
  const updateSession = useCallback(
    (id: string, updates: Partial<DesignSession>): void => {
      setSessions((prev) =>
        prev.map((s) =>
          s.id === id ? { ...s, ...updates, updatedAt: Date.now() } : s,
        ),
      );
    },
    [],
  );

  /** Delete a session */
  const deleteSession = useCallback((id: string): void => {
    setSessions((prev) => prev.filter((s) => s.id !== id));
    setActiveSessionId((current) => (current === id ? null : current));
  }, []);

  /** Set active session */
  const setActiveSession = useCallback((id: string | null): void => {
    setActiveSessionId(id);
  }, []);

  /** Add a new round to a session */
  const addRound = useCallback(
    (sessionId: string, roundData: Omit<DesignRound, "id">): DesignRound => {
      const newRound: DesignRound = {
        ...roundData,
        id: generateId(),
      };
      setSessions((prev) =>
        prev.map((s) =>
          s.id === sessionId
            ? { ...s, rounds: [...s.rounds, newRound], updatedAt: Date.now() }
            : s,
        ),
      );
      return newRound;
    },
    [],
  );

  /** Update an existing round */
  const updateRound = useCallback(
    (
      sessionId: string,
      roundId: string,
      updates: Partial<DesignRound>,
    ): void => {
      setSessions((prev) =>
        prev.map((s) =>
          s.id === sessionId
            ? {
                ...s,
                rounds: s.rounds.map((r) =>
                  r.id === roundId ? { ...r, ...updates } : r,
                ),
                updatedAt: Date.now(),
              }
            : s,
        ),
      );
    },
    [],
  );

  /** Add a candidate to a session's round */
  const addCandidate = useCallback(
    (
      sessionId: string,
      roundId: string,
      candidateData: Omit<
        DesignCandidate,
        "id" | "roundId" | "createdAt"
      >,
    ): DesignCandidate => {
      const newCandidate = createCandidate(roundId, candidateData);
      setSessions((prev) =>
        prev.map((s) =>
          s.id === sessionId
            ? {
                ...s,
                rounds: s.rounds.map((r) =>
                  r.id === roundId
                    ? { ...r, candidates: [...r.candidates, newCandidate] }
                    : r,
                ),
                updatedAt: Date.now(),
              }
            : s,
        ),
      );
      return newCandidate;
    },
    [],
  );

  /** Update an existing candidate */
  const updateCandidate = useCallback(
    (
      sessionId: string,
      roundId: string,
      candidateId: string,
      updates: Partial<DesignCandidate>,
    ): void => {
      setSessions((prev) =>
        prev.map((s) =>
          s.id === sessionId
            ? {
                ...s,
                rounds: s.rounds.map((r) =>
                  r.id === roundId
                    ? {
                        ...r,
                        candidates: r.candidates.map((c) =>
                          c.id === candidateId ? { ...c, ...updates } : c,
                        ),
                      }
                    : r,
                ),
                updatedAt: Date.now(),
              }
            : s,
        ),
      );
    },
    [],
  );

  /** Toggle favorite status */
  const toggleFavorite = useCallback(
    (sessionId: string, candidateId: string): void => {
      setSessions((prev) =>
        prev.map((s) => {
          if (s.id !== sessionId) return s;
          const isFav = s.favorites.includes(candidateId);
          return {
            ...s,
            favorites: isFav
              ? s.favorites.filter((id) => id !== candidateId)
              : [...s.favorites, candidateId],
            updatedAt: Date.now(),
          };
        }),
      );
    },
    [],
  );

  /** Get all candidates from a session */
  const getAllCandidates = useCallback(
    (sessionId: string): DesignCandidate[] => {
      const session = sessions.find((s) => s.id === sessionId);
      if (!session) return [];
      return session.rounds.flatMap((r) => r.candidates);
    },
    [sessions],
  );

  /** Get candidates for a specific round */
  const getRoundCandidates = useCallback(
    (sessionId: string, roundId: string): DesignCandidate[] => {
      const session = sessions.find((s) => s.id === sessionId);
      if (!session) return [];
      const round = session.rounds.find((r) => r.id === roundId);
      return round?.candidates ?? [];
    },
    [sessions],
  );

  /** Get favorite candidates for a session */
  const getFavoriteCandidates = useCallback(
    (sessionId: string): DesignCandidate[] => {
      const session = sessions.find((s) => s.id === sessionId);
      if (!session) return [];
      const allCandidates = session.rounds.flatMap((r) => r.candidates);
      return allCandidates.filter((c) => session.favorites.includes(c.id));
    },
    [sessions],
  );

  /** Find which round a candidate belongs to */
  const findCandidateRound = useCallback(
    (sessionId: string, candidateId: string): DesignRound | undefined => {
      const session = sessions.find((s) => s.id === sessionId);
      if (!session) return undefined;
      return session.rounds.find((r) =>
        r.candidates.some((c) => c.id === candidateId),
      );
    },
    [sessions],
  );

  const value: SessionContextValue = {
    sessions,
    activeSession,
    createSession,
    updateSession,
    deleteSession,
    setActiveSession,
    addRound,
    updateRound,
    addCandidate,
    updateCandidate,
    toggleFavorite,
    getAllCandidates,
    getRoundCandidates,
    getFavoriteCandidates,
    findCandidateRound,
  };

  return (
    <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
  );
}

/** Hook to access session context */
export function useSession(): SessionContextValue {
  const context = useContext(SessionContext);
  if (!context) {
    throw new Error("useSession must be used within a SessionProvider");
  }
  return context;
}

/** Hook to access the active session with convenience helpers */
export function useActiveSession() {
  const {
    activeSession,
    updateSession,
    updateRound,
    addRound,
    addCandidate,
    updateCandidate,
    toggleFavorite,
    getAllCandidates,
    getFavoriteCandidates,
    findCandidateRound,
  } = useSession();

  const currentRound = activeSession?.rounds[activeSession.rounds.length - 1];

  return {
    session: activeSession,
    currentRound,
    updateSession,
    updateRound,
    addRound,
    addCandidate,
    updateCandidate,
    toggleFavorite,
    getAllCandidates,
    getFavoriteCandidates,
    findCandidateRound,
  };
}

export { createEmptySession, createEmptyRound, createCandidate };
