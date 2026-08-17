import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../api";
import type { LlmConfig, LlmSettingsResponse } from "../types/api";

/** Built-in provider presets.
 *  Sources: cross-referenced with cc-switch-main claudeProviderPresets.ts (2026-08).
 *  OpenAI-chat presets use /v1/chat/completions + Bearer token.
 *  Anthropic presets use /v1/messages + x-api-key header + required max_tokens.
 *  ⚠️ = uses ANTHROPIC_API_KEY instead of ANTHROPIC_AUTH_TOKEN (both work via x-api-key). */
type PresetMeta = {
  baseUrl: string;
  model: string;
  icon: string;
  category: "cloud" | "local" | "custom";
  apiFormat: "openai_chat" | "anthropic";
  tier?: "official" | "prime" | "aggregator";
};
const PRESETS: Record<string, PresetMeta> = {
  // ── OpenAI-chat (Bearer /v1/chat/completions) ──────────────────────────────────
  openai: {
    baseUrl: "https://api.openai.com/v1",
    model: "gpt-5.6-luna",
    icon: "◉",
    category: "cloud",
    apiFormat: "openai_chat",
    tier: "official",
  },
  deepseek: {
    baseUrl: "https://api.deepseek.com/v1",
    model: "deepseek-v4-pro",
    icon: "⬡",
    category: "cloud",
    apiFormat: "openai_chat",
  },
  siliconflow: {
    baseUrl: "https://api.siliconflow.cn/v1",
    model: "deepseek-ai/DeepSeek-V4-Pro",
    icon: "◈",
    category: "cloud",
    apiFormat: "openai_chat",
  },
  kimi: {
    baseUrl: "https://api.moonshot.cn/v1",
    model: "kimi-k3",
    icon: "🌙",
    category: "cloud",
    apiFormat: "openai_chat",
  },
  stepfun: {
    baseUrl: "https://api.stepfun.com/v1",
    model: "step-2",
    icon: "⬆",
    category: "cloud",
    apiFormat: "openai_chat",
  },
  zhipu: {
    baseUrl: "https://open.bigmodel.cn/api/paas/v4",
    model: "GLM-5.3",
    icon: "🔷",
    category: "cloud",
    apiFormat: "openai_chat",
  },
  qwen: {
    baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    model: "qwen-plus",
    icon: "◇",
    category: "cloud",
    apiFormat: "openai_chat",
  },
  ollama: {
    baseUrl: "http://localhost:11434/v1",
    model: "llama3.2",
    icon: "⬢",
    category: "local",
    apiFormat: "openai_chat",
  },
  // ── Anthropic (x-api-key /v1/messages + SSE) ───────────────────────────────────
  // Official / Prime partners
  "anthropic-official": {
    baseUrl: "https://api.anthropic.com",
    model: "claude-sonnet-5",
    icon: "🟠",
    category: "cloud",
    apiFormat: "anthropic",
    tier: "official",
  },
  "kimi-anthropic": {
    baseUrl: "https://api.moonshot.cn/anthropic",
    model: "kimi-k2.7-code",
    icon: "🌙",
    category: "cloud",
    apiFormat: "anthropic",
    tier: "prime",
  },
  "kimi-coding": {
    baseUrl: "https://api.kimi.com/coding/",
    model: "kimi-for-coding",
    icon: "🌙",
    category: "cloud",
    apiFormat: "anthropic",
    tier: "prime",
  },
  "doubao-agent-plan": {
    baseUrl: "https://ark.cn-beijing.volces.com/api/plan",
    model: "ark-code-latest",
    icon: "🔥",
    category: "cloud",
    apiFormat: "anthropic",
    tier: "official",
  },
  "doubao-coding-plan": {
    baseUrl: "https://ark.cn-beijing.volces.com/api/coding",
    model: "ark-code-latest",
    icon: "🔥",
    category: "cloud",
    apiFormat: "anthropic",
    tier: "official",
  },
  "doubao-compatible": {
    baseUrl: "https://ark.cn-beijing.volces.com/api/compatible",
    model: "doubao-seed-2-1-pro-260628",
    icon: "🔥",
    category: "cloud",
    apiFormat: "anthropic",
    tier: "official",
  },
  "byteplus": {
    baseUrl: "https://ark.ap-southeast.bytepluses.com/api/coding",
    model: "ark-code-latest",
    icon: "💠",
    category: "cloud",
    apiFormat: "anthropic",
    tier: "official",
  },
  // Baidu
  "baidu-qianfan-coding": {
    baseUrl: "https://qianfan.baidubce.com/anthropic/coding",
    model: "qianfan-code-latest",
    icon: "🔍",
    category: "cloud",
    apiFormat: "anthropic",
    tier: "official",
  },
  "baidu-token-plan": {
    baseUrl: "https://qianfan.baidubce.com/anthropic/tokenplan/personal",
    model: "deepseek-v4-pro",
    icon: "🔍",
    category: "cloud",
    apiFormat: "anthropic",
    tier: "official",
  },
  // Alibaba
  "bailian": {
    baseUrl: "https://dashscope.aliyuncs.com/apps/anthropic",
    model: "",
    icon: "⚙",
    category: "cloud",
    apiFormat: "anthropic",
    tier: "official",
  },
  "bailian-coding": {
    baseUrl: "https://coding.dashscope.aliyuncs.com/apps/anthropic",
    model: "",
    icon: "⚙",
    category: "cloud",
    apiFormat: "anthropic",
    tier: "official",
  },
  // StepFun
  "stepfun-anthropic": {
    baseUrl: "https://api.stepfun.com/step_plan",
    model: "step-3.5-flash-2603",
    icon: "⬆",
    category: "cloud",
    apiFormat: "anthropic",
    tier: "official",
  },
  "stepfun-en": {
    baseUrl: "https://api.stepfun.ai/step_plan",
    model: "step-3.5-flash-2603",
    icon: "⬆",
    category: "cloud",
    apiFormat: "anthropic",
    tier: "official",
  },
  // Zhipu
  "zhipu-glm": {
    baseUrl: "https://open.bigmodel.cn/api/anthropic",
    model: "glm-5.1",
    icon: "🔷",
    category: "cloud",
    apiFormat: "anthropic",
    tier: "official",
  },
  "zhipu-glm-en": {
    baseUrl: "https://api.z.ai/api/anthropic",
    model: "glm-5.1",
    icon: "🔷",
    category: "cloud",
    apiFormat: "anthropic",
    tier: "official",
  },
  // MiniMax
  "minimax-cn": {
    baseUrl: "https://api.minimaxi.com/anthropic",
    model: "MiniMax-M2.7",
    icon: "◆",
    category: "cloud",
    apiFormat: "anthropic",
    tier: "official",
  },
  "minimax-en": {
    baseUrl: "https://api.minimax.io/anthropic",
    model: "MiniMax-M2.7",
    icon: "◆",
    category: "cloud",
    apiFormat: "anthropic",
    tier: "official",
  },
  // ModelScope
  "modelscope": {
    baseUrl: "https://api-inference.modelscope.cn",
    model: "ZhipuAI/GLM-5.2",
    icon: "🔬",
    category: "cloud",
    apiFormat: "anthropic",
    tier: "official",
  },
  // Longcat
  "longcat": {
    baseUrl: "https://api.longcat.chat/anthropic",
    model: "LongCat-2.0",
    icon: "🐱",
    category: "cloud",
    apiFormat: "anthropic",
    tier: "official",
  },
  // Xiaomi MiMo
  "xiaomi-mimo": {
    baseUrl: "https://api.xiaomimimo.com/anthropic",
    model: "mimo-v2.5-pro",
    icon: "📱",
    category: "cloud",
    apiFormat: "anthropic",
    tier: "official",
  },
  // DeepSeek Anthropic
  "deepseek-anthropic": {
    baseUrl: "https://api.deepseek.com/anthropic",
    model: "deepseek-v4-pro",
    icon: "⬡",
    category: "cloud",
    apiFormat: "anthropic",
    tier: "official",
  },
  // OpenRouter
  "openrouter": {
    baseUrl: "https://openrouter.ai/api",
    model: "anthropic/claude-sonnet-5",
    icon: "🌐",
    category: "cloud",
    apiFormat: "anthropic",
  },
  // Third-party / aggregators
  "packycode": {
    baseUrl: "https://www.packyapi.ai",
    model: "",
    icon: "📦",
    category: "cloud",
    apiFormat: "anthropic",
  },
  "zetaapi": {
    baseUrl: "https://api.zetaapi.ai",
    model: "",
    icon: "⚡",
    category: "cloud",
    apiFormat: "anthropic",
  },
  "apinebula": {
    baseUrl: "https://apinebula.ai",
    model: "",
    icon: "🌫",
    category: "cloud",
    apiFormat: "anthropic",
  },
  "aicodemirror": {
    baseUrl: "https://api.aicodemirror.ai/api/claudecode",
    model: "",
    icon: "🪞",
    category: "cloud",
    apiFormat: "anthropic",
  },
  "patewayai": {
    baseUrl: "https://api.pateway.ai",
    model: "",
    icon: "🚪",
    category: "cloud",
    apiFormat: "anthropic",
  },
  "fennoai": {
    baseUrl: "https://api.fenno.ai",
    model: "",
    icon: "🌿",
    category: "cloud",
    apiFormat: "anthropic",
  },
  "runapi": {
    baseUrl: "https://runapi.host",
    model: "",
    icon: "🏃",
    category: "cloud",
    apiFormat: "anthropic",
  },
  "shengsuanyun": {
    baseUrl: "https://router.shengsuanyun.com/api",
    model: "anthropic/claude-sonnet-5",
    icon: "☁",
    category: "cloud",
    apiFormat: "anthropic",
  },
  "aigocode": {
    baseUrl: "https://api.aigocode.app",
    model: "",
    icon: "🤖",
    category: "cloud",
    apiFormat: "anthropic",
  },
  "subrouter": {
    baseUrl: "https://subrouter.ai",
    model: "",
    icon: "🔀",
    category: "cloud",
    apiFormat: "anthropic",
  },
  "apikeyfun": {
    baseUrl: "https://api.apikey.fun",
    model: "",
    icon: "🔑",
    category: "cloud",
    apiFormat: "anthropic",
  },
  "claudeapi": {
    baseUrl: "https://gw.apito.ai",
    model: "",
    icon: "🟣",
    category: "cloud",
    apiFormat: "anthropic",
  },
  "claudecn": {
    baseUrl: "https://claudecn.top",
    model: "",
    icon: "🇨🇳",
    category: "cloud",
    apiFormat: "anthropic",
  },
  "compshare": {
    baseUrl: "https://api.modelverse.cn",
    model: "",
    icon: "🔗",
    category: "cloud",
    apiFormat: "anthropic",
  },
  "compshare-coding": {
    baseUrl: "https://cp.compshare.cn",
    model: "",
    icon: "🔗",
    category: "cloud",
    apiFormat: "anthropic",
  },
  "ccsub": {
    baseUrl: "https://www.ccsub.net",
    model: "",
    icon: "🔶",
    category: "cloud",
    apiFormat: "anthropic",
  },
  "sssaicode": {
    baseUrl: "https://node-hk.sssaicodeapi.com/api",
    model: "",
    icon: "🦋",
    category: "cloud",
    apiFormat: "anthropic",
  },
  "micu": {
    baseUrl: "https://www.micuapi.ai",
    model: "",
    icon: "🎤",
    category: "cloud",
    apiFormat: "anthropic",
  },
  "rightcode": {
    baseUrl: "https://www.rightapi.ai/claude",
    model: "",
    icon: "✅",
    category: "cloud",
    apiFormat: "anthropic",
  },
  "etok": {
    baseUrl: "https://api.etok.ai",
    model: "",
    icon: "🪙",
    category: "cloud",
    apiFormat: "anthropic",
  },
  "cubence": {
    baseUrl: "https://api.cubence.com",
    model: "",
    icon: "🎯",
    category: "cloud",
    apiFormat: "anthropic",
  },
  "crazyrouter": {
    baseUrl: "https://cn.crazyrouter.com",
    model: "",
    icon: "🌀",
    category: "cloud",
    apiFormat: "anthropic",
  },
  "dmxapi": {
    baseUrl: "https://www.dmxapi.cn",
    model: "",
    icon: "💠",
    category: "cloud",
    apiFormat: "anthropic",
  },
  "sudocode-chat": {
    baseUrl: "https://api.sudocode.chat",
    model: "",
    icon: "💬",
    category: "cloud",
    apiFormat: "anthropic",
  },
  "amux": {
    baseUrl: "https://api.amux.ai",
    model: "",
    icon: "🧬",
    category: "cloud",
    apiFormat: "anthropic",
  },
  "cherryin": {
    baseUrl: "https://open.cherryin.net",
    model: "anthropic/claude-sonnet-5",
    icon: "🍒",
    category: "cloud",
    apiFormat: "anthropic",
  },
  "novita-ai": {
    baseUrl: "https://api.novita.ai/anthropic",
    model: "zai-org/glm-5.1",
    icon: "🌟",
    category: "cloud",
    apiFormat: "anthropic",
  },
  "ppio": {
    baseUrl: "https://api.ppio.com/anthropic",
    model: "deepseek/deepseek-v4-flash-0731",
    icon: "🟢",
    category: "cloud",
    apiFormat: "anthropic",
  },
  "jiekouai": {
    baseUrl: "https://api.jiekou.ai/anthropic",
    model: "claude-fable-5",
    icon: "🔌",
    category: "cloud",
    apiFormat: "anthropic",
  },
  "therouter": {
    baseUrl: "https://api.therouter.ai",
    model: "anthropic/claude-sonnet-5",
    icon: "🛤️",
    category: "cloud",
    apiFormat: "anthropic",
  },
  "pipellm": {
    baseUrl: "https://cc-api.pipellm.ai",
    model: "claude-opus-5",
    icon: "📜",
    category: "cloud",
    apiFormat: "anthropic",
  },
  "nvidia-ngc": {
    baseUrl: "https://integrate.api.nvidia.com",
    model: "moonshotai/kimi-k2.5",
    icon: "🟢",
    category: "cloud",
    apiFormat: "openai_chat",
  },
  // ── Custom ─────────────────────────────────────────────────────────────────────
  custom: {
    baseUrl: "",
    model: "",
    icon: "⚙",
    category: "custom",
    apiFormat: "openai_chat",
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
    setCfg((prev) => ({
      ...prev,
      provider: presetKey,
      baseUrl: preset.baseUrl,
      model: preset.model,
      apiFormat: preset.apiFormat,
    }));
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

  // Tier-based sections
  const officialAnthropic = cloudPresets.filter(([, v]) => v.tier === "official" && v.apiFormat === "anthropic");
  const primeAnthropic = cloudPresets.filter(([, v]) => v.tier === "prime" && v.apiFormat === "anthropic");
  const thirdPartyAnthropic = cloudPresets.filter(([, v]) => v.apiFormat === "anthropic" && !v.tier);
  const openaiPresets = cloudPresets.filter(([, v]) => v.apiFormat === "openai_chat");

  return (
    <div className="space-y-5 max-w-2xl">
      {/* Page header */}
      <div>
        <h1 className="text-xl font-semibold text-slate-800">{t("settings.title")}</h1>
        <p className="text-sm text-slate-500 mt-1">{t("settings.subtitle")}</p>
      </div>

      {/* Provider presets */}
      <div className="card p-5">
        <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-4">
          {t("settings.llm.presets")}
        </h2>

        {/* Official Anthropic partners */}
        {(officialAnthropic.length > 0 || primeAnthropic.length > 0) && (
          <>
            <p className="text-[11px] text-amber-600 font-medium mb-2">
              ★ Anthropic /v1/messages — 官方 & 合作平台
            </p>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 mb-4">
              {[...officialAnthropic, ...primeAnthropic].map(([key, meta]) => {
                const isActive = cfg.provider === key;
                return (
                  <button
                    key={key}
                    onClick={() => void handlePreset(key)}
                    className={
                      isActive
                        ? "flex items-center gap-1.5 px-2.5 py-2 rounded-lg border-2 border-brand-500 bg-brand-50 text-brand-700 text-sm font-medium transition-all"
                        : "flex items-center gap-1.5 px-2.5 py-2 rounded-lg border border-amber-300 bg-amber-50 text-slate-600 text-sm hover:border-amber-400 hover:bg-amber-100 transition-all"
                    }
                  >
                    <span className={isActive ? "text-brand-600" : "text-amber-500"} aria-hidden="true">
                      {meta.icon}
                    </span>
                    <span className="truncate">{t(`settings.llm.preset.${key}`, { defaultValue: key })}</span>
                    {isActive && (
                      <span className="ml-auto text-brand-500 shrink-0">✓</span>
                    )}
                  </button>
                );
              })}
            </div>
          </>
        )}

        {/* OpenAI-chat presets */}
        {openaiPresets.length > 0 && (
          <>
            <p className="text-[11px] text-slate-400 font-medium mb-2">OpenAI /v1/chat/completions</p>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 mb-4">
              {openaiPresets.map(([key, meta]) => {
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
                      <span className="ml-auto text-brand-500 shrink-0">✓</span>
                    )}
                  </button>
                );
              })}
            </div>
          </>
        )}

        {/* Other Anthropic third-party */}
        {thirdPartyAnthropic.length > 0 && (
          <>
            <p className="text-[11px] text-slate-400 font-medium mb-2">Anthropic /v1/messages — 第三方聚合</p>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
              {thirdPartyAnthropic.map(([key, meta]) => {
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
                      <span className="ml-auto text-brand-500 shrink-0">✓</span>
                    )}
                  </button>
                );
              })}
            </div>
          </>
        )}

        {/* Custom */}
        {otherPresets.length > 0 && (
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 mt-3">
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
                    <span className="ml-auto text-brand-500 shrink-0">✓</span>
                  )}
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* Manual config */}
      <div className="card p-5">
        <h2 className="text-sm font-semibold text-slate-500 uppercase tracking-wide mb-4">
          {t("settings.llm.config")}
        </h2>

        <div className="grid grid-cols-3 gap-4 mb-4">
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
              placeholder="gpt-5.6-luna"
            />
          </div>
          <div>
            <label className="field-label">API Format</label>
            <select
              className="input text-sm"
              value={cfg.apiFormat}
              onChange={(e) => { setCfg((p) => ({ ...p, apiFormat: e.target.value as "openai_chat" | "anthropic" })); setSaved(false); }}
            >
              <option value="openai_chat">OpenAI Chat (/v1/chat)</option>
              <option value="anthropic">Anthropic (/v1/messages)</option>
            </select>
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
            <p>
              <span className="text-slate-500">API Format: </span>
              <span className="text-slate-800">{defaults.api_format}</span>
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
