import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, ApiClientError } from "../api";
import type { HealthResponse, ModelInfo } from "../types/api";

type ParamType = "string" | "integer" | "number" | "boolean" | "null" | "array";

function schemaType(schema: Record<string, unknown>): ParamType {
  const t = schema.type as string | string[] | undefined;
  if (Array.isArray(t)) return (t.filter((x) => x !== "null")[0] as ParamType) ?? "string";
  return (t as ParamType) ?? "string";
}

function schemaEnum(schema: Record<string, unknown>): string[] | null {
  const e = schema.enum;
  return Array.isArray(e) && e.every((x) => typeof x === "string") ? (e as string[]) : null;
}

interface FormField {
  key: string;
  schema: Record<string, unknown>;
  type: ParamType;
  enumValues: string[] | null;
  title: string;
  titleKey?: string;
  default: unknown;
  description: string;
  descriptionKey?: string;
  required?: boolean;
}

function collectFields(paramSchema: Record<string, unknown>): FormField[] {
  const props = (paramSchema.properties ?? {}) as Record<string, Record<string, unknown>>;
  const required = (paramSchema.required as string[] | undefined) ?? [];
  return Object.entries(props).map(([key, s]) => {
    const schema = s as Record<string, unknown>;
    return {
      key,
      schema,
      type: schemaType(schema),
      enumValues: schemaEnum(schema),
      title: (schema.title as string) ?? key,
      titleKey: (schema.title_key as string) || undefined,
      default: schema.default,
      description: (schema.description as string) ?? "",
      descriptionKey: (schema.description_key as string) || undefined,
      required: required.includes(key),
    };
  });
}

function FieldInput({
  field,
  value,
  onChange,
}: {
  field: FormField;
  value: unknown;
  onChange: (v: unknown) => void;
}) {
  const { t } = useTranslation();
  const titleText = field.titleKey
    ? t(field.titleKey, { defaultValue: field.title })
    : field.title;
  const descText =
    field.descriptionKey && field.description
      ? t(field.descriptionKey, { defaultValue: field.description })
      : field.description;
  const label = (
    <label className="block text-sm font-medium text-slate-700 mb-1">
      {titleText}
      {field.required && <span className="text-red-500 ml-0.5">*</span>}
      {!field.required && (
        <span className="text-slate-400 text-xs font-normal ml-1.5">({t("common.optional")})</span>
      )}
    </label>
  );

  if (field.enumValues) {
    return (
      <div>
        {label}
        <select
          className="w-full border border-surface-border rounded-md px-3 py-2 text-sm bg-white focus:ring-2 focus:ring-brand-500"
          value={String(value ?? "")}
          onChange={(e) => onChange(e.target.value)}
        >
          {field.enumValues.map((v) => (
            <option key={v} value={v}>
              {v}
            </option>
          ))}
        </select>
        {descText && (
          <p className="text-xs text-slate-400 mt-1">{descText}</p>
        )}
      </div>
    );
  }

  if (field.type === "boolean") {
    return (
      <div className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={Boolean(value)}
          onChange={(e) => onChange(e.target.checked)}
          className="h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
        />
        <span className="text-sm text-slate-600">{titleText}</span>
      </div>
    );
  }

  if (field.type === "integer" || field.type === "number") {
    const min = field.schema.minimum as number | undefined;
    const max = field.schema.maximum as number | undefined;
    return (
      <div>
        {label}
        <input
          type="number"
          min={min}
          max={max}
          step={field.type === "number" ? "any" : 1}
          value={value === undefined || value === null ? "" : String(value)}
          onChange={(e) => {
            const raw = e.target.value;
            if (raw === "") {
              onChange(null);
              return;
            }
            onChange(field.type === "integer" ? parseInt(raw, 10) : parseFloat(raw));
          }}
          className="w-full border border-surface-border rounded-md px-3 py-2 text-sm bg-white focus:ring-2 focus:ring-brand-500"
        />
        {descText && (
          <p className="text-xs text-slate-400 mt-1">{descText}</p>
        )}
      </div>
    );
  }

  // string
  return (
    <div>
      {label}
      <input
        type="text"
        value={value === undefined || value === null ? "" : String(value)}
        onChange={(e) => onChange(e.target.value)}
        className="w-full border border-surface-border rounded-md px-3 py-2 text-sm bg-white focus:ring-2 focus:ring-brand-500"
      />
      {descText && (
        <p className="text-xs text-slate-400 mt-1">{descText}</p>
      )}
    </div>
  );
}

export function HomePage({ health }: { health: HealthResponse | null }) {
  const { t } = useTranslation();
  const [models, setModels] = useState<ModelInfo[] | null>(null);
  const [selected, setSelected] = useState<string>("rfd3");
  const [params, setParams] = useState<Record<string, unknown>>({});
  const [advanced, setAdvanced] = useState(false);
  const [advancedJson, setAdvancedJson] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [fileRole, setFileRole] = useState("structure");
  const [jobName, setJobName] = useState("");
  const [engineMode, setEngineMode] = useState("auto");
  const [submitting, setSubmitting] = useState(false);
  const [notice, setNotice] = useState<{ kind: "ok" | "err"; text: string } | null>(null);
  const [createdJobId, setCreatedJobId] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api
      .models()
      .then((m) => {
        setModels(m);
        if (m.length > 0) {
          setSelected(m[0].id);
          setParams(m[0].param_defaults ?? {});
        }
      })
      .catch((e) => setNotice({ kind: "err", text: String(e) }));
  }, []);

  const model = useMemo(
    () => models?.find((m) => m.id === selected) ?? null,
    [models, selected],
  );

  const fields = useMemo(() => (model ? collectFields(model.param_schema) : []), [model]);

  const switchModel = (id: string) => {
    setSelected(id);
    const m = models?.find((x) => x.id === id);
    setParams(m?.param_defaults ?? {});
    setAdvancedJson("");
    setNotice(null);
  };

  const selectFiles = (list: FileList | null) => {
    if (!list) return;
    setFiles((prev) => {
      const names = new Set(prev.map((f) => f.name));
      const merged = [...prev];
      for (const f of Array.from(list)) {
        if (!names.has(f.name)) {
          merged.push(f);
          names.add(f.name);
        }
      }
      return merged;
    });
  };

  const buildParams = (): Record<string, unknown> => {
    if (advanced) {
      try {
        return JSON.parse(advancedJson || "{}");
      } catch {
        throw new Error("json-parse");
      }
    }
    return { ...params };
  };

  const handleSubmit = async () => {
    if (!model) {
      setNotice({ kind: "err", text: t("home.validation.needModel") });
      return;
    }
    setNotice(null);
    setSubmitting(true);
    try {
      const p = buildParams();
      const job = await api.createJob({
        model: model.id,
        name: jobName || undefined,
        params: p,
        engine_mode: engineMode as "auto" | "real" | "simulation",
      });
      if (files.length > 0) {
        await api.uploadFiles(job.id, files, fileRole);
      }
      const submitted = await api.submitJob(job.id);
      setCreatedJobId(submitted.id);
      setNotice({ kind: "ok", text: t("home.submitSuccess") });
      setFiles([]);
      setJobName("");
    } catch (e) {
      const msg =
        e instanceof ApiClientError
          ? e.body.message
          : e instanceof Error && e.message === "json-parse"
            ? t("home.advancedError", { detail: "invalid JSON" })
            : String(e);
      setNotice({ kind: "err", text: msg });
    } finally {
      setSubmitting(false);
    }
  };

  if (!models) {
    return (
      <div className="py-20 text-center text-slate-400">
        {t("common.loading")}
        {!health && <p className="mt-2 text-sm">{t("common.serverUnreachable")}</p>}
      </div>
    );
  }

  return (
    <div className="grid lg:grid-cols-[320px_1fr] gap-6">
      {/* Model selection */}
      <aside className="space-y-2">
        <h2 className="text-lg font-semibold text-slate-800">{t("home.model")}</h2>
        {models.map((m) => (
          <button
            key={m.id}
            onClick={() => switchModel(m.id)}
            className={`w-full text-left border rounded-lg p-3 transition-colors ${
              selected === m.id
                ? "border-brand-600 bg-brand-50"
                : "border-surface-border bg-white hover:bg-surface-alt"
            }`}
          >
            <div className="flex items-center justify-between">
              <span className="font-medium text-slate-800 text-sm">
                {m.name_key ? t(m.name_key, { defaultValue: m.name }) : m.name}
              </span>
              <span
                className={`text-[10px] px-1.5 py-0.5 rounded ${
                  m.checkpoint_state === "installed"
                    ? "bg-green-100 text-green-700"
                    : "bg-amber-100 text-amber-700"
                }`}
              >
                {m.checkpoint_state === "installed" ? t("environment.installed") : t("environment.missing")}
              </span>
            </div>
            {selected === m.id && (
              <div className="mt-2 text-xs text-slate-500 space-y-1">
                <p>
                  {t("home.modelDescription")}:{" "}
                  {m.description_key
                    ? t(m.description_key, { defaultValue: m.description })
                    : m.description}
                </p>
                <p>
                  {t("home.capabilities")}:{" "}
                  {m.capabilities
                    .map((c, i) =>
                      m.capability_keys?.[i]
                        ? t(m.capability_keys[i], { defaultValue: c })
                        : c,
                    )
                    .join(", ")}
                </p>
                <p>
                  {t("jobDetail.engineMode")}:{" "}
                  {m.effective_engine === "real"
                    ? t("app.realMode")
                    : t("app.simulationMode")}
                </p>
                {m.checkpoint_state !== "installed" && (
                  <p className="text-amber-600">{t("home.checkpointMissing")}</p>
                )}
              </div>
            )}
          </button>
        ))}
      </aside>

      {/* Form */}
      <section className="bg-white border border-surface-border rounded-lg p-5 space-y-5">
        <div>
          <h2 className="text-lg font-semibold text-slate-800">{t("home.title")}</h2>
          <p className="text-sm text-slate-500">{t("home.subtitle")}</p>
        </div>

        {model && (
          <>
            {/* Job name */}
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">{t("home.jobName")}</label>
              <input
                type="text"
                value={jobName}
                onChange={(e) => setJobName(e.target.value)}
                placeholder={t("home.jobNamePlaceholder")}
                className="w-full border border-surface-border rounded-md px-3 py-2 text-sm bg-white focus:ring-2 focus:ring-brand-500"
              />
            </div>

            {/* Engine mode */}
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">{t("home.engineMode")}</label>
              <select
                value={engineMode}
                onChange={(e) => setEngineMode(e.target.value)}
                className="w-full border border-surface-border rounded-md px-3 py-2 text-sm bg-white focus:ring-2 focus:ring-brand-500"
              >
                <option value="auto">{t("home.engineAuto")}</option>
                <option value="real">{t("home.engineReal")}</option>
                <option value="simulation">{t("home.engineSimulation")}</option>
              </select>
            </div>

            {/* Advanced toggle */}
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="advanced-toggle"
                checked={advanced}
                onChange={(e) => {
                  setAdvanced(e.target.checked);
                  if (e.target.checked && Object.keys(params).length > 0) {
                    setAdvancedJson(JSON.stringify(params, null, 2));
                  }
                }}
                className="h-4 w-4 rounded border-slate-300 text-brand-600"
              />
              <label htmlFor="advanced-toggle" className="text-sm text-slate-600">
                {t("home.advancedToggle")}
              </label>
            </div>

            {advanced ? (
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">{t("home.advanced")}</label>
                <p className="text-xs text-slate-400 mb-1">{t("home.advancedHint")}</p>
                <textarea
                  value={advancedJson}
                  onChange={(e) => setAdvancedJson(e.target.value)}
                  rows={12}
                  spellCheck={false}
                  className="w-full font-mono text-xs border border-surface-border rounded-md p-3 bg-slate-50 focus:ring-2 focus:ring-brand-500"
                />
              </div>
            ) : (
              <div className="grid sm:grid-cols-2 gap-4">
                {fields.map((f) => (
                  <FieldInput
                    key={f.key}
                    field={f}
                    value={params[f.key]}
                    onChange={(v) => setParams((prev) => ({ ...prev, [f.key]: v }))}
                  />
                ))}
              </div>
            )}

            {/* File upload */}
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">{t("home.inputFiles")}</label>
              <p className="text-xs text-slate-400 mb-2">
                {t("home.inputFilesHint", { exts: model.accepted_extensions.join(", ") })}
              </p>
              <div className="flex gap-2 items-center mb-2">
                <select
                  value={fileRole}
                  onChange={(e) => setFileRole(e.target.value)}
                  className="border border-surface-border rounded-md px-2 py-1.5 text-sm bg-white"
                >
                  <option value="structure">{t("home.roleStructure")}</option>
                  {model.id !== "rf3" && <option value="scaffold">{t("home.roleScaffold")}</option>}
                  {model.id !== "rf3" && <option value="motif">{t("home.roleMotif")}</option>}
                  {model.id === "rf3" && <option value="sequence">{t("home.roleSequence")}</option>}
                </select>
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  className="text-sm px-3 py-1.5 border border-surface-border rounded-md bg-white hover:bg-surface-alt"
                >
                  {t("home.dropHere")}
                </button>
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  accept={model.accepted_extensions.map((e) => `.${e}`).join(",")}
                  className="hidden"
                  onChange={(e) => selectFiles(e.target.files)}
                />
              </div>
              {files.length > 0 ? (
                <ul className="text-sm text-slate-600 space-y-1">
                  <li className="text-slate-500">{t("home.uploaded")}</li>
                  {files.map((f) => (
                    <li key={f.name} className="flex items-center gap-2">
                      <span>{f.name}</span>
                      <span className="text-xs text-slate-400">({(f.size / 1024).toFixed(1)} KB)</span>
                      <button
                        className="text-red-500 text-xs hover:underline"
                        onClick={() => setFiles((prev) => prev.filter((x) => x.name !== f.name))}
                      >
                        {t("common.cancel")}
                      </button>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-slate-400">{t("home.noFiles")}</p>
              )}
            </div>

            {notice && (
              <div
                className={`text-sm rounded-md px-3 py-2 ${
                  notice.kind === "ok"
                    ? "bg-green-50 text-green-700 border border-green-200"
                    : "bg-red-50 text-red-700 border border-red-200"
                }`}
              >
                {notice.text}
                {createdJobId && notice.kind === "ok" && (
                  <a
                    className="ml-2 underline"
                    href={`#/jobs/${createdJobId}`}
                  >
                    {t("jobs.view")} →
                  </a>
                )}
              </div>
            )}

            <button
              onClick={() => void handleSubmit()}
              disabled={submitting}
              className="w-full sm:w-auto px-6 py-2.5 bg-brand-600 hover:bg-brand-700 disabled:opacity-50 text-white rounded-md text-sm font-medium"
            >
              {submitting ? t("home.submitting") : t("home.submit")}
            </button>
          </>
        )}
      </section>
    </div>
  );
}
