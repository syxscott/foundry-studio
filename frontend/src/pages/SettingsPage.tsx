import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, ApiClientError } from "../api";
import { toast } from "../components/Toaster";
import type { LlmSettingsResponse } from "../types/api";

function KeyStatus({ present }: { present: boolean }) {
  const { t } = useTranslation();
  return present ? (
    <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full">
      {t("settings.llm.keyPresent")}
    </span>
  ) : (
    <span className="text-xs bg-red-100 text-red-700 px-2 py-0.5 rounded-full">
      {t("settings.llm.keyMissing")}
    </span>
  );
}

export function SettingsPage() {
  const { t } = useTranslation();
  const [settings, setSettings] = useState<LlmSettingsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [apiKeyInput, setApiKeyInput] = useState("");
  const [apiKeySaved, setApiKeySaved] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setSettings(await api.llmSettings());
    } catch (e) {
      setError(e instanceof ApiClientError ? e.body.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const handleSaveApiKey = async () => {
    if (!apiKeyInput.trim()) return;
    setSaving(true);
    setError(null);
    setApiKeySaved(false);
    try {
      const envVar = settings?.api_key_env ?? "OPENAI_API_KEY";
      // Write to a local .env file in the backend working directory so it persists.
      const res = await fetch("/api/settings/write-env", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ env_var: envVar, value: apiKeyInput.trim() }),
      });
      if (!res.ok) {
        const body = (await res.json().catch(() => ({}))) as { message?: string };
        throw new Error(body.message ?? `HTTP ${res.status}`);
      }
      setApiKeySaved(true);
      setApiKeyInput("");
      toast.success(t("settings.llm.apiKeySaved"));
      await load();
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
      toast.error(t("settings.llm.apiKeySaveFailed"), msg);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-xl font-semibold text-slate-800">{t("settings.title")}</h1>
        <p className="text-sm text-slate-500">{t("settings.subtitle")}</p>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-md px-3 py-2">
          {error}
        </div>
      )}

      {/* LLM Provider Section */}
      <div className="card">
        <h2 className="text-base font-semibold text-slate-700 mb-4">{t("settings.llm.title")}</h2>

        {loading ? (
          <p className="text-slate-400">{t("common.loading")}</p>
        ) : settings ? (
          <div className="space-y-4">
            {/* Current config */}
            <div className="bg-surface-alt rounded-lg p-4 space-y-2 text-sm">
              <div className="flex items-center gap-2">
                <span className="text-slate-500 w-28 shrink-0">{t("settings.llm.provider")}:</span>
                <span className="font-mono text-slate-700">{settings.provider}</span>
                {!settings.configured && (
                  <span className="text-xs bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full">
                    {t("settings.llm.notConfigured")}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2">
                <span className="text-slate-500 w-28 shrink-0">{t("settings.llm.baseUrl")}:</span>
                <span className="font-mono text-slate-700 text-xs break-all">{settings.base_url}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-slate-500 w-28 shrink-0">{t("settings.llm.model")}:</span>
                <span className="font-mono text-slate-700">{settings.model}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-slate-500 w-28 shrink-0">{t("settings.llm.keyEnvVar")}:</span>
                <code className="font-mono text-xs bg-slate-100 px-1.5 py-0.5 rounded">
                  {settings.api_key_env}
                </code>
                <KeyStatus present={settings.key_present} />
              </div>
              <div className="flex items-center gap-2">
                <span className="text-slate-500 w-28 shrink-0">{t("settings.llm.timeout")}:</span>
                <span className="text-slate-700">{settings.timeout}s</span>
              </div>
            </div>

            {/* Status summary */}
            {settings.configured && !settings.key_present ? (
              <div className="bg-amber-50 border border-amber-200 text-amber-700 text-sm rounded-md px-3 py-2">
                {t("settings.llm.configuredNoKey")}
              </div>
            ) : !settings.configured ? (
              <div className="bg-slate-50 border border-slate-200 text-slate-600 text-sm rounded-md px-3 py-2">
                {t("settings.llm.notConfiguredDetail")}
              </div>
            ) : null}

            {/* API Key Input */}
            <div className="border-t border-surface-border pt-4">
              <label className="block text-sm font-medium text-slate-700 mb-1.5">
                {t("settings.llm.apiKeyLabel", { envVar: settings.api_key_env })}
              </label>
              <p className="text-xs text-slate-500 mb-2">
                {t("settings.llm.apiKeyHelp")}
              </p>
              <div className="flex gap-2">
                <input
                  type="password"
                  className="input flex-1"
                  placeholder={t("settings.llm.apiKeyPlaceholder")}
                  value={apiKeyInput}
                  onChange={(e) => {
                    setApiKeyInput(e.target.value);
                    setApiKeySaved(false);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !saving) void handleSaveApiKey();
                  }}
                />
                <button
                  className="btn-primary disabled:opacity-50"
                  disabled={saving || !apiKeyInput.trim()}
                  onClick={() => void handleSaveApiKey()}
                >
                  {saving ? t("common.saving") : t("settings.llm.saveKey")}
                </button>
              </div>
              {apiKeySaved && (
                <p className="text-xs text-green-600 mt-1">{t("settings.llm.apiKeySaved")}</p>
              )}
            </div>

            {/* Restart hint */}
            {apiKeySaved && (
              <div className="bg-blue-50 border border-blue-200 text-blue-700 text-sm rounded-md px-3 py-2">
                {t("settings.llm.restartHint")}
              </div>
            )}

            {/* Manual config instructions */}
            <details className="group border-t border-surface-border pt-3">
              <summary className="text-sm text-slate-500 cursor-pointer hover:text-slate-700 list-none flex items-center gap-1">
                <span className="text-xs group-open:hidden">▶</span>
                <span className="text-xs hidden group-open:block">▼</span>
                {t("settings.llm.manualConfig")}
              </summary>
              <div className="mt-2 text-xs text-slate-500 font-mono bg-slate-50 rounded p-3 space-y-1">
                <p># {t("settings.llm.envExampleNote")}</p>
                <p>{settings.api_key_env}=sk-your-key-here</p>
                <p>FOUNDRY_STUDIO_AGENT_LLM_BASE_URL=https://api.deepseek.com/v1</p>
                <p>FOUNDRY_STUDIO_AGENT_LLM_MODEL=deepseek-chat</p>
                <p className="mt-2 text-slate-400">
                  # {t("settings.llm.envLocation", { dir: "foundry-studio/backend/.env" })}
                </p>
              </div>
            </details>
          </div>
        ) : null}
      </div>
    </div>
  );
}
