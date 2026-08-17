/** Toast notification system.

A tiny event-bus + portal-style component. Mount once near the root; any
component can call `toast(...)` to surface a transient message.

- Four kinds: info / success / warning / error
- Auto-dismiss after `ttl` ms (default 4500), but can be sticky
- Click ✕ to dismiss manually
- Stacks at the bottom-right; newest on top
*/

import { useEffect, useRef, useState } from "react";

type ToastKind = "info" | "success" | "warning" | "error";
interface Toast {
  id: number;
  kind: ToastKind;
  title: string;
  body?: string;
  ttl: number;
  sticky: boolean;
  createdAt: number;
}

type ToastInput = Omit<Toast, "id" | "ttl" | "sticky" | "createdAt"> & {
  ttl?: number;
  sticky?: boolean;
};

const KIND_STYLES: Record<ToastKind, { box: string; dot: string }> = {
  info: {
    box: "bg-white border-slate-200 text-slate-800",
    dot: "bg-slate-400",
  },
  success: {
    box: "bg-white border-emerald-200 text-slate-800",
    dot: "bg-emerald-500",
  },
  warning: {
    box: "bg-amber-50 border-amber-200 text-amber-900",
    dot: "bg-amber-500",
  },
  error: {
    box: "bg-red-50 border-red-200 text-red-800",
    dot: "bg-red-500",
  },
};

class ToastBus {
  private listeners = new Set<(t: Toast[]) => void>();
  private toasts: Toast[] = [];
  private nextId = 1;

  subscribe(cb: (t: Toast[]) => void) {
    this.listeners.add(cb);
    cb(this.toasts);
    return () => {
      this.listeners.delete(cb);
    };
  }

  push(input: ToastInput): number {
    const id = this.nextId++;
    const toast: Toast = {
      id,
      kind: input.kind,
      title: input.title,
      body: input.body,
      ttl: input.ttl ?? 4500,
      sticky: input.sticky ?? false,
      createdAt: Date.now(),
    };
    this.toasts = [toast, ...this.toasts].slice(0, 6);
    this.emit();
    return id;
  }

  dismiss(id: number) {
    this.toasts = this.toasts.filter((t) => t.id !== id);
    this.emit();
  }

  clear() {
    this.toasts = [];
    this.emit();
  }

  private emit() {
    for (const cb of this.listeners) cb(this.toasts);
  }
}

export const toastBus = new ToastBus();

/** Convenience helpers. */
export const toast = {
  info: (title: string, body?: string) => toastBus.push({ kind: "info", title, body }),
  success: (title: string, body?: string) => toastBus.push({ kind: "success", title, body }),
  warning: (title: string, body?: string) => toastBus.push({ kind: "warning", title, body }),
  error: (title: string, body?: string) => toastBus.push({ kind: "error", title, body }),
  dismiss: (id: number) => toastBus.dismiss(id),
  clear: () => toastBus.clear(),
};

export function Toaster() {
  const [toasts, setToasts] = useState<Toast[]>([]);
  useEffect(() => toastBus.subscribe(setToasts), []);

  // Track active timers in a ref so unmount can always clear them.
  const timersRef = useRef<ReturnType<typeof setTimeout>[]>([]);

  useEffect(() => {
    // Clear previous timers whenever the toast list changes.
    timersRef.current.forEach(clearTimeout);
    timersRef.current = [];

    if (toasts.length === 0) return;
    const timers = toasts
      .filter((t) => !t.sticky)
      .map((t) => {
        const remaining = Math.max(0, t.ttl - (Date.now() - t.createdAt));
        return setTimeout(() => toastBus.dismiss(t.id), remaining);
      });
    timersRef.current = timers;
    return () => timers.forEach(clearTimeout);
  }, [toasts]);

  // Cleanup on unmount — prevents memory leaks if the component is ever
  // removed while toasts are still pending.
  useEffect(() => {
    return () => timersRef.current.forEach(clearTimeout);
  }, []);

  return (
    <div
      className="fixed bottom-4 right-4 z-[60] flex flex-col-reverse gap-2 w-80 max-w-[calc(100vw-2rem)] pointer-events-none"
      aria-live="polite"
    >
      {toasts.map((t) => {
        const style = KIND_STYLES[t.kind];
        return (
          <div
            key={t.id}
            className={`pointer-events-auto rounded-lg border shadow-md px-3 py-2.5 flex items-start gap-2 animate-toast-in ${style.box}`}
            role="status"
          >
            <span className={`mt-1.5 w-2 h-2 rounded-full shrink-0 ${style.dot}`} />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium leading-tight">{t.title}</p>
              {t.body && <p className="text-xs mt-0.5 opacity-80 break-words">{t.body}</p>}
            </div>
            <button
              type="button"
              onClick={() => toastBus.dismiss(t.id)}
              className="text-xs opacity-60 hover:opacity-100 shrink-0"
              aria-label="Dismiss"
            >
              ✕
            </button>
          </div>
        );
      })}
    </div>
  );
}
