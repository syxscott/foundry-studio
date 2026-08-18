import { useEffect, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { api, ApiClientError } from "../api";
import type { AgentPlan, LlmProviderStatus } from "../types/api";

/** Animated cursor for live streaming text (matches hermes-agent style). */
function StreamingCursor(): ReactNode {
  return (
    <span
      aria-hidden
      className="inline-block w-0.5 h-4 bg-brand-500 ml-0.5 align-[-0.1em] animate-pulse"
    />
  );
}

/** Lightweight inline markdown: **bold**, *italic*, `code`. No external deps. */
function inlineMarkdown(text: string): ReactNode[] {
  const segments: ReactNode[] = [];
  const re = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) segments.push(text.slice(last, m.index));
    const chunk = m[0];
    if (chunk.startsWith("**") && chunk.endsWith("**")) {
      segments.push(<strong key={segments.length}>{chunk.slice(2, -2)}</strong>);
    } else if (chunk.startsWith("`") && chunk.endsWith("`")) {
      segments.push(
        <code key={segments.length} className="text-[11px] bg-slate-100 px-1 rounded font-mono">
          {chunk.slice(1, -1)}
        </code>,
      );
    } else {
      segments.push(<em key={segments.length}>{chunk.slice(1, -1)}</em>);
    }
    last = m.index + chunk.length;
  }
  if (last < text.length) segments.push(text.slice(last));
  return segments;
}

/** Render multi-line text with inline markdown and line breaks. */
function renderThinking(text: string, streaming?: boolean): ReactNode {
  const lines = text.split("\n");
  return (
    <>
      {lines.map((line, i) => (
        <span key={i}>
          {inlineMarkdown(line)}
          {i < lines.length - 1 && <br />}
        </span>
      ))}
      {streaming && <StreamingCursor />}
    </>
  );
}

function Row({ k, v }: { k: string; v: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 py-1.5 border-b border-surface-border last:border-0">
      <span className="text-xs text-slate-400 font-mono shrink-0">{k}</span>
      <span className="text-sm text-slate-700 text-right break-all">{v}</span>
    </div>
  );
}

export default function AgentPanel({ onSubmitted }: { onSubmitted: (jobId: string) => void }) {
  const { t, i18n } = useTranslation();
  const abortControllerRef = useRef<AbortController | null>(null);
  const [text, setText] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [thinking, setThinking] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [plan, setPlan] = useState<AgentPlan | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [errorKey, setErrorKey] = useState<string | null>(null);
  const [errorArgs, setErrorArgs] = useState<Record<string, unknown> | null>(null);
  const [providers, setProviders] = useState<LlmProviderStatus[] | null>(null);

  const EXAMPLES = [
    t("agent.example.1"),
    t("agent.example.2"),
    t("agent.example.3"),
    t("agent.example.4"),
  ];

  // Surface which third-party LLM provider is wired up (or that we're heuristic-only).
  useEffect(() => {
    let active = true;
    api
      .agentCapabilities()
      .then((cap) => {
        if (active) setProviders(cap.providers ?? []);
      })
      .catch(() => {
        if (active) setProviders([]);
      });
    return () => {
      active = false;
    };
  }, []);

  // Cancel any in-flight SSE stream when the component unmounts.
  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
    };
  }, []);

  // Translate a stream error into a localized display string.  Prefer the
  // server-provided i18n key (so the user sees the same wording the rest
  // of the API uses); fall back to the server's already-localized `message`
  // and finally to the raw string.
  const renderError = (): string => {
    if (errorKey) {
      // i18next's TFunction expects string|number|boolean args; server-side
      // errorArgs is `Record<string, unknown>`, so we narrow with a cast.
      const args = (errorArgs ?? {}) as Record<string, string | number | boolean>;
      const template = t(`errors.${errorKey}` as never, args);
      if (template && template !== `errors.${errorKey}`) return template as string;
    }
    return error ?? "";
  };

  const parse = () => {
    if (!text.trim() || streaming) return;
    const controller = new AbortController();
    abortControllerRef.current = controller;
    setStreaming(true);
    setThinking("");
    setError(null);
    setErrorKey(null);
    setErrorArgs(null);
    setPlan(null);
    api.streamAgentChat(text.trim(), i18n.language, {
      signal: controller.signal,
      onToken: (chunk) => setThinking((prev) => prev + chunk),
      onPlan: (p) => {
        setPlan(p);
        setStreaming(false);
      },
      onError: (msg, meta) => {
        setError(msg);
        setErrorKey(meta?.i18nErrorKey ?? null);
        setErrorArgs(meta?.errorArgs ?? null);
        setStreaming(false);
      },
      onDone: () => setStreaming(false),
    });
  };

  // Re-run the planner with the same text. Distinct from `parse` only in
  // that it doesn't require the user to scroll back to the textarea — the
  // error block surfaces a "Retry" button.
  const retry = () => {
    abortControllerRef.current?.abort();
    void parse();
  };

  const submit = async () => {
    if (!plan) return;
    setSubmitting(true);
    setError(null);
    try {
      const job = await api.agentRun({
        model: plan.model,
        name: plan.name,
        params: plan.params,
        resources: plan.resources,
        invocation: plan.invocation,
        lang: i18n.language,
        api_key: api.llmConfig.get().apiKey || undefined,
        base_url: api.llmConfig.get().baseUrl || undefined,
        llm_model: api.llmConfig.get().model || undefined,
        api_format: api.llmConfig.get().apiFormat || undefined,
      });
      onSubmitted(job.id);
    } catch (e) {
      if (e instanceof ApiClientError) setError(e.body.message);
      else setError(String(e));
    } finally {
      setSubmitting(false);
    }
  };

  const paramEntries = plan ? Object.entries(plan.params) : [];
  const resourceEntries = plan ? Object.entries(plan.resources) : [];
  const invocationEntries = plan ? Object.entries(plan.invocation) : [];

  return (
    <section className="card p-5 animate-fade-in">
      <div className="flex items-center gap-2 mb-1">
        <span className="inline-flex items-center justify-center w-7 h-7 rounded-lg bg-brand-50 text-brand-600">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 3v3M12 18v3M3 12h3M18 12h3" />
            <circle cx="12" cy="12" r="4" />
          </svg>
        </span>
        <h2 className="text-base font-semibold text-slate-800">{t("agent.title")}</h2>
        <span className="ml-auto text-[11px] px-2 py-0.5 rounded-full bg-accent-50 text-accent-700 font-medium">
          {plan ? plan.resolved_by : "NL → JobSpec"}
        </span>
      </div>
      <p className="text-xs text-slate-500 mb-3">{t("agent.subtitle")}</p>

      {/* Third-party LLM provider status (visible "API connected" signal). */}
      {providers && (
        <div className="mb-3 text-[11px] flex flex-wrap items-center gap-1.5">
          {providers.length === 0 ? (
            <span className="px-2 py-0.5 rounded-full bg-slate-100 text-slate-500">
              {t("agent.llmOff")}
            </span>
          ) : (
            providers.map((p) => (
              <span
                key={p.name}
                className={`px-2 py-0.5 rounded-full font-medium ${
                  p.key_present
                    ? "bg-emerald-50 text-emerald-700"
                    : "bg-amber-50 text-amber-700"
                }`}
                title={p.base_url}
              >
                {p.key_present
                  ? t("agent.llmOk", { name: p.name })
                  : t("agent.llmNoKey", { name: p.name })}
              </span>
            ))
          )}
        </div>
      )}

      <textarea
        className="input h-24 resize-none"
        placeholder={t("agent.inputPlaceholder")}
        value={text}
        onChange={(e) => setText(e.target.value)}
      />

      <div className="flex flex-wrap gap-1.5 mt-2">
        {EXAMPLES.map((ex) => (
          <button
            key={ex}
            className="text-[11px] px-2.5 py-1 rounded-full border border-surface-border text-slate-500 hover:bg-surface-alt transition-colors"
            onClick={() => setText(ex)}
          >
            {ex.length > 32 ? ex.slice(0, 32) + "…" : ex}
          </button>
        ))}
      </div>

      <div className="flex gap-2 mt-3">
        <button
          className="btn-primary"
          onClick={() => void parse()}
          disabled={streaming || !text.trim()}
        >
          {streaming ? t("agent.thinking") : t("agent.parse")}
        </button>
        {plan && (
          <button className="btn-soft" onClick={() => setPlan(null)}>
            {t("agent.clear")}
          </button>
        )}
      </div>

      {error && (
        <div className="mt-3 text-xs text-red-600 bg-red-50 border border-red-100 rounded-md px-3 py-2 flex items-start justify-between gap-2">
          <span className="flex-1">{renderError()}</span>
          {!streaming && (
            <button
              type="button"
              className="text-[11px] font-medium text-red-700 hover:text-red-800 underline shrink-0"
              onClick={retry}
            >
              {t("common.retry")}
            </button>
          )}
        </div>
      )}

      {/* Live "thinking" stream from the LLM. */}
      {!plan && (streaming || thinking) && (
        <div className="mt-4 rounded-lg border border-brand-200 bg-brand-50/40 p-4 animate-fade-in-up">
          <div className="flex items-center gap-2 mb-2">
            <span className="flex gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-brand-400 animate-pulse" />
              <span className="w-1.5 h-1.5 rounded-full bg-brand-400 animate-pulse" style={{ animationDelay: "150ms" }} />
              <span className="w-1.5 h-1.5 rounded-full bg-brand-400 animate-pulse" style={{ animationDelay: "300ms" }} />
            </span>
            <span className="text-xs uppercase tracking-wide text-brand-600 font-semibold">
              {t("agent.thinking")}
            </span>
            {streaming && (
              <span className="ml-auto inline-flex items-center gap-1 text-[10px] text-brand-500 font-medium">
                <span className="w-1.5 h-1.5 rounded-full bg-brand-500 animate-soft-pulse" />
                {t("designSession.round.live", { defaultValue: "live" })}
              </span>
            )}
          </div>
          <pre className="text-sm text-slate-700 leading-relaxed max-h-48 overflow-auto scroll-thin">
            {renderThinking(thinking || "…", streaming)}
          </pre>
        </div>
      )}

      {plan && (
        <div className="mt-4 rounded-lg border border-brand-200 bg-brand-50/40 p-4">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-xs uppercase tracking-wide text-brand-600 font-semibold">
              {t("agent.planTitle")}
            </span>
            <span className="text-sm font-medium text-slate-800">{plan.model}</span>
          </div>

          {paramEntries.length > 0 && (
            <div className="mt-1">
              <p className="text-[11px] font-semibold text-slate-400 mb-1">{t("agent.plan.params")}</p>
              <div className="bg-white rounded-md px-3">
                {paramEntries.map(([k, v]) => (
                  <Row key={k} k={k} v={String(v)} />
                ))}
              </div>
            </div>
          )}

          {resourceEntries.length > 0 && (
            <div className="mt-3">
              <p className="text-[11px] font-semibold text-slate-400 mb-1">{t("agent.plan.resources")}</p>
              <div className="bg-white rounded-md px-3">
                {resourceEntries.map(([k, v]) => (
                  <Row key={k} k={k} v={String(v)} />
                ))}
              </div>
            </div>
          )}

          {invocationEntries.length > 0 && (
            <div className="mt-3">
              <p className="text-[11px] font-semibold text-slate-400 mb-1">{t("agent.plan.invocation")}</p>
              <div className="bg-white rounded-md px-3">
                {invocationEntries.map(([k, v]) => (
                  <Row key={k} k={k} v={String(v)} />
                ))}
              </div>
            </div>
          )}

          {plan.warnings.length > 0 && (
            <div className="mt-3 text-xs text-amber-700 bg-amber-50 border border-amber-100 rounded-md px-3 py-2">
              <span className="font-medium">{t("agent.plan.warnings")}:</span> {plan.warnings.join("；")}
            </div>
          )}
          {plan.missing_inputs.length > 0 && (
            <div className="mt-2 text-xs text-red-600 bg-red-50 border border-red-100 rounded-md px-3 py-2">
              <span className="font-medium">{t("agent.plan.missing")}:</span> {plan.missing_inputs.join("；")}
            </div>
          )}

          {plan.resolved_by === "llm" && (
            <p className="text-xs text-slate-500 mt-2">
              {t("agent.planLlmmNote")}
            </p>
          )}

          <button
            className="btn-primary w-full mt-4"
            onClick={() => void submit()}
            disabled={submitting}
          >
            {submitting ? t("agent.submitting") : t("agent.submit")}
          </button>
        </div>
      )}

      <div className="mt-4 text-[11px] text-slate-400 leading-relaxed border-t border-surface-border pt-3">
        <span className="font-medium text-slate-500">{t("agent.externalTitle")}</span>{" "}
        {t("agent.externalHint")}
        <code className="ml-1 px-1.5 py-0.5 rounded bg-slate-100 text-slate-500 font-mono">
          POST /api/agent/run
        </code>
      </div>
    </section>
  );
}
