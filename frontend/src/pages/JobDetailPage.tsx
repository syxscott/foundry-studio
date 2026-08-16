import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, ApiClientError } from "../api";
import { StatusBadge } from "../components/StatusBadge";
import { StructureViewer } from "../components/StructureViewer";
import type { Job } from "../types/api";

const POLL_MS = 2000;

export function JobDetailPage({
  jobId,
  onBack,
}: {
  jobId: string;
  onBack: () => void;
}) {
  const { t } = useTranslation();
  const [job, setJob] = useState<Job | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [logs, setLogs] = useState("");
  const [viewUrl, setViewUrl] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const logRef = useRef<HTMLPreElement>(null);
  const lastLogLenRef = useRef(0);

  const load = useCallback(async () => {
    try {
      const j = await api.getJob(jobId);
      setJob(j);
      setNotFound(false);
      // Refresh logs if present.
      if (j.logs_url || j.status === "running" || j.status === "succeeded" || j.status === "failed") {
        try {
          const lr = await api.getLogs(jobId);
          if (lr.logs !== logs) setLogs(lr.logs);
        } catch {
          /* logs endpoint may 404 for draft jobs */
        }
      }
    } catch (e) {
      if (e instanceof ApiClientError && e.status === 404) setNotFound(true);
      else setActionError(e instanceof ApiClientError ? e.body.message : String(e));
    }
  }, [jobId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    void load();
    const id = setInterval(() => void load(), POLL_MS);
    return () => clearInterval(id);
  }, [load]);

  // Auto-scroll the log panel on new content.
  useEffect(() => {
    if (logRef.current && logs.length > lastLogLenRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
    lastLogLenRef.current = logs.length;
  }, [logs]);

  const handleSubmit = async () => {
    try {
      setJob(await api.submitJob(jobId));
    } catch (e) {
      setActionError(e instanceof ApiClientError ? e.body.message : String(e));
    }
  };

  const handleCancel = async () => {
    if (!window.confirm(t("jobs.confirmCancel", { name: job?.name ?? jobId }))) return;
    try {
      await api.cancelJob(jobId);
      setJob(await api.getJob(jobId));
    } catch (e) {
      setActionError(e instanceof ApiClientError ? e.body.message : String(e));
    }
  };

  const handleDelete = async () => {
    if (!window.confirm(t("jobs.confirmDelete", { name: job?.name ?? jobId }))) return;
    try {
      await api.deleteJob(jobId);
      onBack();
    } catch (e) {
      setActionError(e instanceof ApiClientError ? e.body.message : String(e));
    }
  };

  const downloadAll = () => {
    if (!job || job.outputs.length === 0) return;
    // The backend zips every output; Content-Disposition: attachment triggers
    // the browser download.
    window.location.href = api.downloadJobZip(job.id);
  };

  if (notFound) {
    return (
      <div className="py-20 text-center">
        <p className="text-slate-500">{t("jobDetail.notFound")}</p>
        <button className="mt-4 text-brand-600 underline text-sm" onClick={onBack}>
          {t("jobDetail.back")}
        </button>
      </div>
    );
  }

  if (!job) {
    return <p className="py-20 text-center text-slate-400">{t("common.loading")}</p>;
  }

  const cifOutputs = job.outputs.filter((o) => o.kind === "cif");
  const fastaOutputs = job.outputs.filter((o) => o.kind === "fasta");

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <button className="text-sm text-slate-500 hover:text-brand-600" onClick={onBack}>
          ← {t("jobDetail.back")}
        </button>
        <h1 className="text-xl font-semibold text-slate-800">
          {job.name || job.id.slice(0, 12)}
        </h1>
        <StatusBadge status={job.status} />
        {job.engine_mode === "simulation" && (
          <span className="text-[11px] bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full">
            {t("app.simulationMode")}
          </span>
        )}
      </div>

      {actionError && (
        <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-md px-3 py-2">
          {actionError}
        </div>
      )}

      {job.engine_mode === "simulation" && job.status === "succeeded" && (
        <div className="bg-amber-50 border border-amber-200 text-amber-800 text-sm rounded-md px-3 py-2">
          {t("jobDetail.simulationWarning")}
        </div>
      )}

      {/* Meta grid */}
      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <Meta label={t("jobDetail.model")} value={job.model} mono />
        <Meta label={t("jobDetail.engineMode")} value={job.engine_mode} mono />
        <Meta label={t("jobDetail.createdAt")} value={new Date(job.created_at).toLocaleString()} />
        <Meta
          label={t("jobDetail.progress")}
          value={job.progress != null ? `${job.progress}%` : "—"}
        />
        {job.started_at && <Meta label={t("jobDetail.startedAt")} value={new Date(job.started_at).toLocaleString()} />}
        {job.finished_at && <Meta label={t("jobDetail.finishedAt")} value={new Date(job.finished_at).toLocaleString()} />}
      </div>

      {job.error_detail && (
        <div className="bg-red-50 border border-red-200 rounded-md p-3">
          <p className="text-sm font-medium text-red-800">{t("jobDetail.error")}</p>
          <pre className="text-xs text-red-700 mt-1 whitespace-pre-wrap font-mono">{job.error_detail}</pre>
        </div>
      )}

      {/* Actions */}
      {(job.status === "draft" || job.status === "queued") && (
        <div className="flex gap-2">
          {job.status === "draft" && (
            <button
              className="px-4 py-2 bg-brand-600 hover:bg-brand-700 text-white rounded-md text-sm"
              onClick={() => void handleSubmit()}
            >
              {t("jobDetail.actions.submit")}
            </button>
          )}
          <button
            className="px-4 py-2 border border-amber-300 text-amber-700 rounded-md text-sm hover:bg-amber-50"
            onClick={() => void handleCancel()}
          >
            {t("jobDetail.actions.cancel")}
          </button>
        </div>
      )}
      {(job.status === "succeeded" || job.status === "failed" || job.status === "canceled") && (
        <button
          className="px-4 py-2 border border-red-200 text-red-600 rounded-md text-sm hover:bg-red-50"
          onClick={() => void handleDelete()}
        >
          {t("jobDetail.actions.delete")}
        </button>
      )}

      {/* Input files */}
      {job.input_files.length > 0 && (
        <Section title={t("jobDetail.inputFiles")}>
          <ul className="text-sm text-slate-600 space-y-1">
            {job.input_files.map((f) => (
              <li key={f.filename} className="font-mono text-xs">
                [{f.role}] {f.filename}
              </li>
            ))}
          </ul>
        </Section>
      )}

      {/* Outputs */}
      <Section title={t("jobDetail.outputs")}>
        {job.outputs.length === 0 ? (
          <p className="text-sm text-slate-400">{t("jobDetail.noOutputs")}</p>
        ) : (
          <div className="space-y-2">
            <div className="flex flex-wrap gap-2">
              {cifOutputs.map((o) => (
                <button
                  key={o.url}
                  className="text-xs px-3 py-1.5 bg-brand-50 text-brand-700 border border-brand-200 rounded-md hover:bg-brand-100"
                  onClick={() => setViewUrl(o.url)}
                >
                  {t("jobDetail.view3d")} · {o.name}
                </button>
              ))}
              {job.outputs.length > 0 && (
                <button
                  className="text-xs px-3 py-1.5 border border-surface-border rounded-md hover:bg-surface-alt"
                  onClick={() => void downloadAll()}
                >
                  {t("jobDetail.actions.downloadAll")}
                </button>
              )}
            </div>
            <ul className="text-sm space-y-1">
              {job.outputs.map((o) => (
                <li key={o.url} className="flex items-center gap-2">
                  <span className="font-mono text-xs text-slate-600">{o.name}</span>
                  <span className="text-[10px] text-slate-400">
                    {o.kind} · {(o.size_bytes / 1024).toFixed(1)} KB
                  </span>
                  <a className="text-brand-600 text-xs hover:underline" href={o.url} download>
                    {t("jobDetail.download")}
                  </a>
                </li>
              ))}
            </ul>
            {fastaOutputs.length > 0 && <FastaPreview url={fastaOutputs[0].url} />}
          </div>
        )}
      </Section>

      {/* Logs */}
      <Section title={t("jobDetail.logs")}>
        {logs ? (
          <pre
            ref={logRef}
            className="bg-slate-900 text-slate-100 text-xs p-3 rounded-md overflow-auto max-h-64 scroll-thin font-mono"
          >
            {logs}
          </pre>
        ) : (
          <p className="text-sm text-slate-400">{t("jobDetail.logsEmpty")}</p>
        )}
      </Section>

      {viewUrl && <StructureViewer url={viewUrl} onClose={() => setViewUrl(null)} />}
    </div>
  );
}

function Meta({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="bg-white border border-surface-border rounded-md px-3 py-2">
      <p className="text-xs text-slate-400">{label}</p>
      <p className={`text-sm text-slate-700 mt-0.5 ${mono ? "font-mono" : ""}`}>{value}</p>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-white border border-surface-border rounded-lg p-4">
      <h3 className="text-sm font-semibold text-slate-700 mb-2">{title}</h3>
      {children}
    </div>
  );
}

function FastaPreview({ url }: { url: string }) {
  const { t } = useTranslation();
  const [text, setText] = useState<string | null>(null);

  useEffect(() => {
    fetch(url)
      .then((r) => r.text())
      .then((x) => setText(x.slice(0, 4000)))
      .catch(() => setText(""));
  }, [url]);

  if (text === null) return null;
  return (
    <details className="mt-2">
      <summary className="text-xs text-slate-500 cursor-pointer select-none">
        {t("jobDetail.detail")}
      </summary>
      <pre className="mt-2 bg-slate-50 border border-surface-border text-xs p-3 rounded-md overflow-auto max-h-48 font-mono whitespace-pre-wrap">
        {text}
      </pre>
    </details>
  );
}
