/** Design Session types for iterative protein design workflow. */

export interface DesignCandidate {
  /** Unique identifier for this candidate */
  id: string;
  /** Display name of the candidate */
  name: string;
  /** Protein sequence (amino acid string) */
  sequence: string;
  /** Optional human-readable description of this candidate */
  description?: string;
  /** ID of the round this candidate belongs to */
  roundId: string;
  /** Associated job ID if a job was submitted for this candidate */
  jobId?: string;
  /** URL to the structure file (CIF) from job outputs */
  structureUrl?: string;
  /** Whether this candidate is favorited by the user */
  isFavorite?: boolean;
  /** Optional key-value annotations (e.g., model used, metrics) */
  annotations?: Record<string, string>;
  /** Timestamp when this candidate was created (ms since epoch) */
  createdAt: number;
}

export interface DesignRound {
  /** Unique identifier for this round */
  id: string;
  /** The user's message/prompt that initiated this round */
  userMessage: string;
  /** The AI's response (may be streaming) */
  aiMessage: string;
  /** Whether the AI response is still streaming */
  isStreaming?: boolean;
  /** Candidates proposed in this round */
  candidates: DesignCandidate[];
  /** How the round was resolved */
  resolvedBy: "llm" | "heuristic";
  /** Associated job ID if jobs were run for this round */
  jobId?: string;
}

export interface DesignSession {
  /** Unique identifier for this session */
  id: string;
  /** User-defined or auto-generated session name */
  name: string;
  /** Timestamp when session was created (ms since epoch) */
  createdAt: number;
  /** Timestamp when session was last updated (ms since epoch) */
  updatedAt: number;
  /** All rounds in this session */
  rounds: DesignRound[];
  /** IDs of favorited candidates */
  favorites: string[];
  /** Session status */
  status: "active" | "archived";
}

/** Filter options for candidate list */
export type CandidateFilter = "all" | "favorites" | "thisRound";

/** Candidate comparison selection state */
export interface CandidateComparisonState {
  /** Whether comparison mode is active */
  isActive: boolean;
  /** IDs of selected candidates (max 3) */
  selectedIds: string[];
}

/** Form data for creating a new candidate job */
export interface CandidateJobForm {
  /** Candidate to submit as job */
  candidate: DesignCandidate;
  /** Optional custom job name */
  jobName?: string;
  /** Engine mode override */
  engineMode?: "auto" | "real" | "simulation";
}
