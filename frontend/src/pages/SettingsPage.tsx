import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../api";
import type { LlmConfig, LlmSettingsResponse } from "../types/api";

/** Built-in OpenAI-compatible provider presets.
 *  Sources: cross-referenced with cc-switch-main / volcengine / MiniMax / StepFun official docs (2026-08).
 *  All use standard /v1/chat/completions + Bearer token — no special SDK needed. */
type PresetMeta = { baseUrl: string; model: string; icon: string; category: "cloud" | "local" | "custom" };
const PRESETS: Record<string, PresetMeta> = {
  deepseek: {
    baseUrl: "https://api.deepseek.com/v1",
    model: "deepseek-chat",
    icon: "⬡",
    category: "cloud",
  },
  openai: {
    baseUrl: "https://api.openai.com/v1",
    model: "gpt-5.4-mini",
    icon: "◉",
    category: "cloud",
  },
  "openai-gpt4o": {
    baseUrl: "https://api.openai.com/v1",
    model: "gpt-5.6-terra",
    icon: "◉",
    category: "cloud",
  },
  siliconflow: {
    baseUrl: "https://api.siliconflow.cn/v1",
    model: "deepseek-ai/DeepSeek-V3",
    icon: "◈",
    category: "cloud",
  },
  kimi: {
    // Moonshot AI — OpenAI-compatible; kimi-k3 (1M, multimodal), kimi-k2.6 (256k, coding/agentic)
    baseUrl: "https://api.moonshot.cn/v1",
    model: "kimi-k2.6",
    icon: "🌙",
    category: "cloud",
  },
  stepfun: {
    // 阶跃星辰 — step-2 (LiveBench国产第一, 128k)
    baseUrl: "https://api.stepfun.com/v1",
    model: "step-2",
    icon: "⬆",
    category: "cloud",
  },
  zhipu: {
    // 智谱 GLM — GLM-5.2 (2026-06, 1M上下文)
    baseUrl: "https://open.bigmodel.cn/api/paas/v4",
    model: "GLM-5.2",
    icon: "🔷",
    category: "cloud",
  },
  yi: {
    // 零一万物 — OpenAI-compatible; yi-lightning (性价比), yi-large (旗舰)
    baseUrl: "https://api.lingyiwanwu.com/v1",
    model: "yi-large",
    icon: "✦",
    category: "cloud",
  },
  baichuan: {
    // 百川智能 — OpenAI-compatible; Baichuan4 (旗舰)
    baseUrl: "https://api.baichuan-ai.com/v1",
    model: "Baichuan4",
    icon: "◈",
    category: "cloud",
  },
  minimax: {
    // MiniMax — MiniMax-M3 (2026 旗舰, 1M上下文, Agent/Coding), MiniMax-M2.7 (均衡)
    baseUrl: "https://api.minimax.io/v1",
    model: "MiniMax-M3",
    icon: "◆",
    category: "cloud",
  },
  qwen: {
    // 阿里通义 — compatible-mode 端点; qwen-max-latest (旗舰), qwen-plus (均衡)
    baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    model: "qwen-plus",
    icon: "◇",
    category: "cloud",
  },
  "doubao-pro": {
    // 火山引擎方舟 — Doubao Seed 2.1 Pro 旗舰款 (256k, 深度推理/Agent/多模态)
    baseUrl: "https://ark.cn-beijing.volces.com/api/v3",
    model: "doubao-seed-2-1-pro-260628",
    icon: "🔥",
    category: "cloud",
  },
  "doubao-code": {
    // 火山引擎方舟 Coding Plan — 专为 Claude Code/Cursor 等编程工具优化
    baseUrl: "https://ark.cn-beijing.volces.com/api/coding",
    model: "ark-code-latest",
    icon: "🔥",
    category: "cloud",
  },
  ollama: {
    baseUrl: "http://localhost:11434/v1",
    model: "llama3.2",
    icon: "⬢",
    category: "local",
  },
  custom: {
    baseUrl: "",
    model: "",
    icon: "⚙",
    category: "custom",
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

  useEffect(() => {
    api.llmSettings()
      .then((d) => {
        setDefaults(d);
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

  const cloudPresets = Object.entries(PRESETS).filter(([, v]) => v.category === "cloud");
  const otherPresets = Object.entries(PRESETS).filter(([, v]) => v.category !== "cloud");

  return (
    <div className="space-y-5 max-w-2xl">
      {/* Page header */}
      <div>
        <h1 className="text-xl font-semibold text-slate-800">{t("settings.title")}</h1>
        <p className="text-sm text-slate-500 mt-1">{t("settings.subtitle")}</p>
      </div>

      {/* Provider presets — 3-col compact grid */}
      <div className="card p-5">
        <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-4">
          {t("settings.llm.presets")}
        </h2>

        {/* Primary cloud presets: 3-col */}
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 mb-3">
          {cloudPresets.map(([key, meta]) => {
            const isActive = cfg.provider === key;
            return (
              <button
                key={key}
                onClick={() => void handlePreset(key)}
                className={
                  isActive
                    ? "flex items-center gap-1.5 px-2.5 py-2 rounded-lg border-2 border-brand-500 bg-brand-50 text-brand-700 text-sm font-medium transition-all"
                    : "flex items-center gap-1.5 px-2.5 py-2 rounded-lg border border-surface-border bg-white text-slate-600 text-sm hover:border-brand-400 hover:bg-brand-50/50 transition-all"
                }
              >
                <span className={isActive ? "text-brand-600" : "text-slate-400"} aria-hidden="true">
                  {meta.icon}
                </span>
                <span className="truncate">{t(`settings.llm.preset.${key}`, { defaultValue: key })}</span>
                {isActive && (
                  <span className="ml-auto text-brand-500 shrink-0" aria-label="已选择">
                    ✓
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {/* Secondary / local / custom: 3-col */}
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
          {otherPresets.map(([key, meta]) => {
            const isActive = cfg.provider === key;
            return (
              <button
                key={key}
                onClick={() => void handlePreset(key)}
                className={
                  isActive
                    ? "flex items-center gap-1.5 px-2.5 py-2 rounded-lg border-2 border-brand-500 bg-brand-50 text-brand-700 text-sm font-medium transition-all"
                    : "flex items-center gap-1.5 px-2.5 py-2 rounded-lg border border-surface-border bg-white text-slate-600 text-sm hover:border-brand-400 hover:bg-brand-50/50 transition-all"
                }
              >
                <span className={isActive ? "text-brand-600" : "text-slate-400"} aria-hidden="true">
                  {meta.icon}
                </span>
                <span className="truncate">{t(`settings.llm.preset.${key}`, { defaultValue: key })}</span>
                {isActive && (
                  <span className="ml-auto text-brand-500 shrink-0" aria-label="已选择">
                    ✓
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* Manual config */}
      <div className="card p-5">
        <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-4">
          {t("settings.llm.config")}
        </h2>

        <div className="grid grid-cols-2 gap-4 mb-4">
          <div>
            <label className="field-label">{t("settings.llm.baseUrl")}</label>
            <input
              type="url"
              className="input font-mono text-xs"
              value={cfg.baseUrl}
              onChange={(e) => { setCfg((p) => ({ ...p, baseUrl: e.target.value })); setSaved(false); }}
              placeholder="https://api.openai.com/v1"
            />
          </div>
          <div>
            <label className="field-label">{t("settings.llm.model")}</label>
            <input
              type="text"
              className="input font-mono text-sm"
              value={cfg.model}
              onChange={(e) => { setCfg((p) => ({ ...p, model: e.target.value })); setSaved(false); }}
              placeholder="gpt-4o-mini"
            />
          </div>
        </div>

        <div className="mb-5">
          <label className="field-label">{t("settings.llm.apiKey")}</label>
          <p className="text-xs text-slate-500 mt-1">{t("settings.llm.apiKeyHelp")}</p>
          <input
            type="password"
            className="input font-mono text-sm mt-1"
            value={cfg.apiKey}
            onChange={(e) => { setCfg((p) => ({ ...p, apiKey: e.target.value })); setSaved(false); }}
            placeholder={t("settings.llm.apiKeyPlaceholder")}
          />
          <div className="mt-1.5 flex items-center gap-2">
            <KeyStatus hasKey={hasKey} />
            {!hasKey && (
              <span className="text-xs text-amber-600">{t("settings.llm.keyRequired")}</span>
            )}
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            className="btn-primary disabled:opacity-50"
            disabled={saving}
            onClick={() => void handleSave()}
          >
            {saving ? t("common.saving") : t("common.save")}
          </button>
          {saved && (
            <span className="text-sm text-green-600 font-medium">{t("settings.llm.saved")}</span>
          )}
        </div>
      </div>

      {/* Backend defaults */}
      {loadingDefaults ? null : defaults ? (
        <div className="card p-5">
          <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-3">
            {t("settings.llm.backendDefaults")}
          </h2>
          <p className="text-xs text-slate-400 mb-3">{t("settings.llm.backendDefaultsHelp")}</p>
          <div className="bg-surface-alt rounded-lg p-3 space-y-1.5 text-xs font-mono text-slate-600">
            <p>
              <span className="text-slate-500">{t("settings.llm.provider")}: </span>
              <span className="text-slate-800">{defaults.provider}</span>
            </p>
            <p>
              <span className="text-slate-500">{t("settings.llm.baseUrl")}: </span>
              <span className="text-slate-800">{defaults.base_url}</span>
            </p>
            <p>
              <span className="text-slate-500">{t("settings.llm.model")}: </span>
              <span className="text-slate-800">{defaults.model}</span>
            </p>
          </div>
          <p className="text-xs text-slate-400 mt-3">{t("settings.llm.priorityNote")}</p>
        </div>
      ) : null}

      {/* Tip */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg px-4 py-3 text-xs text-blue-700">
        {t("settings.llm.tip")}
      </div>
    </div>
  );
}
