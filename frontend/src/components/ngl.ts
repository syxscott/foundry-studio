/**
 * Lazy NGL loader.
 *
 * NGL is a ~810 KB (uncompressed) 3D/WebGL library used by only two optional
 * components (`StructureViewer`, `CandidateComparison`). Importing it statically
 * put it in the entry chunk, so every visitor downloaded ~half a megabyte of
 * molecular-graphics code even on pages that never open a structure viewer.
 *
 * Keeping the dynamic import here means both components share one code-split
 * chunk that Rollup fetches on demand, and browsers cache it after the first
 * structure view.
 */

type NglModule = typeof import("ngl");

let pending: Promise<NglModule> | null = null;

/** Load (and memoize) the NGL module. Concurrent callers share one request. */
export function loadNgl(): Promise<NglModule> {
  if (!pending) {
    pending = import("ngl").catch((err) => {
      // Don't cache a failure: a transient network error should be retryable.
      pending = null;
      throw err;
    });
  }
  return pending;
}

export type { NglModule };
