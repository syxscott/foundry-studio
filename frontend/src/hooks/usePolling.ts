import { useEffect, useRef } from "react";

/**
 * Run an async function on a timer, correctly.
 *
 * Two properties this gives us that a raw `setInterval` does not:
 *
 * 1. **No overlapping runs.** The next timer is scheduled only after the
 *    previous call settles, so a slow or hung backend can't stack up duplicate
 *    requests (which previously multiplied load the slower the server got).
 * 2. **No state updates after unmount.** The effect's `cancelled` flag is
 *    checked before and after the awaited call.
 *
 * `delayFor` lets the caller back off when nothing is happening:
 * `(active: boolean) => ms`. Returning `null`/`0` pauses polling entirely.
 *
 * @param fn        async work to run on each tick
 * @param delayFor  interval in ms, or a function of the previous run's return
 *                  value when adaptive cadence is wanted
 * @param enabled   when false, polling is suspended (e.g. no data to watch yet)
 */
export function usePolling<T>(
  fn: () => Promise<T>,
  delayFor: number | ((result: T) => number),
  enabled = true,
): void {
  // Keep the latest fn without restarting the timer on every render.
  const fnRef = useRef(fn);
  fnRef.current = fn;

  useEffect(() => {
    if (!enabled) return;

    let timer: ReturnType<typeof setTimeout> | null = null;
    let cancelled = false;

    const tick = async () => {
      if (cancelled) return;
      let result: T;
      try {
        result = await fnRef.current();
      } catch {
        // Swallow: callers surface their own error state. Still keep polling.
        result = undefined as T;
      }
      if (cancelled) return;
      const delay =
        typeof delayFor === "function" ? delayFor(result) : delayFor;
      if (delay > 0) timer = setTimeout(() => void tick(), delay);
    };

    void tick();

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [delayFor, enabled]);
}
