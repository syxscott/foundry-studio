import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../api";
import type { LlmConfig, LlmSettingsResponse } from "../types/api";

/** Built-in provider presets. */
const PRESETS: Record<string, { baseUrl: string; model: string }> = {
  deepseek: {
    baseUrl: "https://api.deepseek.com/v1",
    model: "deepseek-chat",
  },
  openai: {
    baseUrl: "https://api.openai.com/v1",
    model: "gpt-4o-mini",
  },
  "openai-gpt4o": {
    baseUrl: "https://api.openai.com/v1",
    model: "gpt-4o",
  },
  siliconflow: {
    baseUrl: "https://api.siliconflow.cn/v1",
    model: "deepseek-ai/DeepSeek-V3",
  },
  ollama: {
    baseUrl: "http://localhost:11434/v1",
    model: "llama3.2",
  },
  custom: {
    baseUrl: "",
    model: "",
  },
};

function KeyStatus({ hasKey }: { hasKey: boolean }) {
  const { t } = useTranslation();
  return hasKey ? (
    <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full">
      {t("settings.llm.keySet")}
    </span>
  ) : (
    <span className="text-xs bg-red-100 text-red-700 px-2 py-0.5 rounded-full">
      {t("settings.llm.keyMissing")}
    </span>
  );
}

export function SettingsPage() {
  const { t } = useTranslation();
  const [defaults, setDefaults] = useState<LlmSettingsResponse | null>(null);
  const [cfg, setCfg] = useState<LlmConfig>(() => api.llmConfig.get());
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [loadingDefaults, setLoadingDefaults] = useState(true);

  // Load backend defaults (read-only, just for display)
  useEffect(() => {
    api.llmSettings()
      .then((d) => {
        setDefaults(d);
        // Seed from localStorage if empty, otherwise keep user's choice
      })
      .catch(() => {/* non-fatal */})
      .finally(() => setLoadingDefaults(false));
  }, []);

  const handlePreset = useCallback((presetKey: string) => {
    const preset = PRESETS[presetKey];
    if (!preset) return;
    setCfg((prev) => ({ ...prev, provider: presetKey, baseUrl: preset.baseUrl, model: preset.model }));
    setSaved(false);
  }, []);

  const handleSave = useCallback(async () => {
    setSaving(true);
    try {
      api.llmConfig.set(cfg);
      setSaved(true);
    } finally {
      setSaving(false);
    }
  }, [cfg]);

  const hasKey = cfg.apiKey.trim().length > 0;

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-xl font-semibold text-slate-800">{t("settings.title")}</h1>
        <p className="text-sm text-slate-500">{t("settings.subtitle")}</p>
      </div>

      {/* Presets */}
      <div className="card">
        <h2 className="text-base font-semibold text-slate-700 mb-3">{t("settings.llm.presets")}</h2>
        <div className="flex flex-wrap gap-2">
          {Object.entries(PRESETS).map(([key, _]) => (
            <button
              key={key}
              className={`px-3 py-1.5 rounded-full text-sm border transition-colors ${
                cfg.provider === key
                  ? "bg-brand-600 text-white border-brand-600"
                  : "border-surface-border text-slate-600 hover:bg-surface-alt"
              }`}
              onClick={() => void handlePreset(key)}
            >
              {t(`settings.llm.preset.${key}`, { defaultValue: key })}
            </button>
          ))}
        </div>
      </div>

      {/* Config form */}
      <div className="card space-y-4">
        <h2 className="text-base font-semibold text-slate-700">{t("settings.llm.config")}</h2>

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">
            {t("settings.llm.baseUrl")}
          </label>
          <input
            type="url"
            className="input w-full font-mono text-xs"
            value={cfg.baseUrl}
            onChange={(e) => { setCfg((p) => ({ ...p, baseUrl: e.target.value })); setSaved(false); }}
            placeholder="https://api.openai.com/v1"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">
            {t("settings.llm.model")}
          </label>
          <input
            type="text"
            className="input w-full font-mono text-sm"
            value={cfg.model}
            onChange={(e) => { setCfg((p) => ({ ...p, model: e.target.value })); setSaved(false); }}
            placeholder="gpt-4o-mini"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">
            {t("settings.llm.apiKey")}
          </label>
          <p className="text-xs text-slate-500 mb-2">{t("settings.llm.apiKeyHelp")}</p>
          <input
            type="password"
            className="input w-full font-mono text-sm"
            value={cfg.apiKey}
            onChange={(e) => { setCfg((p) => ({ ...p, apiKey: e.target.value })); setSaved(false); }}
            placeholder={t("settings.llm.apiKeyPlaceholder")}
          />
          <div className="mt-1.5 flex items-center gap-2">
            <KeyStatus hasKey={hasKey} />
            {!hasKey && (
              <span className="text-xs text-amber-600">
                {t("settings.llm.keyRequired")}
              </span>
            )}
          </div>
        </div>

        <div className="flex items-center gap-3 pt-2">
          <button
            className="btn-primary disabled:opacity-50"
            disabled={saving}
            onClick={() => void handleSave()}
          >
            {saving ? t("common.saving") : t("common.save")}
          </button>
          {saved && (
            <span className="text-sm text-green-600">{t("settings.llm.saved")}</span>
          )}
        </div>
      </div>

      {/* Backend defaults info (read-only) */}
      {loadingDefaults ? null : defaults ? (
        <div className="card">
          <h2 className="text-base font-semibold text-slate-700 mb-2">{t("settings.llm.backendDefaults")}</h2>
          <p className="text-xs text-slate-500 mb-3">{t("settings.llm.backendDefaultsHelp")}</p>
          <div className="bg-surface-alt rounded-lg p-3 space-y-1.5 text-xs font-mono text-slate-600">
            <p>{t("settings.llm.provider")}: <span className="text-slate-800">{defaults.provider}</span></p>
            <p>{t("settings.llm.baseUrl")}: <span className="text-slate-800">{defaults.base_url}</span></p>
            <p>{t("settings.llm.model")}: <span className="text-slate-800">{defaults.model}</span></p>
          </div>
          <p className="text-xs text-slate-400 mt-2">
            {t("settings.llm.priorityNote")}
          </p>
        </div>
      ) : null}

      {/* Tip */}
      <div className="bg-blue-50 border border-blue-200 rounded-md px-3 py-2 text-xs text-blue-700">
        {t("settings.llm.tip")}
      </div>
    </div>
  );
}
