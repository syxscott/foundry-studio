import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { api, ApiClientError } from "../api";
import type { AgentChatResponse } from "../types/api";

const EXAMPLES = [
  "用 RFD3 设计一个 80 残基的 binder，针对 hotspot A12/B34，采样 5 个",
  "Predict the structure of this protein with RF3",
  "用 ProteinMPNN 对 1abc.pdb 做序列设计，温度 0.2",
  "用 RFD3na 生成 3 个核酸结合蛋白",
];

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
  const [text, setText] = useState("");
  const [parsing, setParsing] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [plan, setPlan] = useState<AgentChatResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const parse = async () => {
    if (!text.trim()) return;
    setParsing(true);
    setError(null);
    setPlan(null);
    try {
      const res = await api.agentChat(text.trim(), i18n.language);
      setPlan(res);
    } catch (e) {
      if (e instanceof ApiClientError) setError(e.body.message);
      else setError(String(e));
    } finally {
      setParsing(false);
    }
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
          disabled={parsing || !text.trim()}
        >
          {parsing ? t("agent.parsing") : t("agent.parse")}
        </button>
        {plan && (
          <button
            className="btn-soft"
            onClick={() => setPlan(null)}
          >
            {t("agent.clear")}
          </button>
        )}
      </div>

      {error && (
        <div className="mt-3 text-xs text-red-600 bg-red-50 border border-red-100 rounded-md px-3 py-2">
          {error}
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
