import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, ApiClientError } from "../api";
import type { CheckpointInfo } from "../types/api";

function formatSize(
  bytes: number | null | undefined,
  t: (key: string, opts?: Record<string, unknown>) => string,
): string {
  if (bytes == null) return "—";
  const gb = bytes / 1024 ** 3;
  if (gb >= 1) return t("environment.sizeGb", { size: gb.toFixed(2) });
  const mb = bytes / 1024 ** 2;
  if (mb >= 1) return t("environment.sizeMb", { size: mb.toFixed(1) });
  return t("environment.sizeBytes", { size: bytes });
}

export function EnvironmentPage() {
  const { t } = useTranslation();
  const [items, setItems] = useState<CheckpointInfo[] | null>(null);
  const [installing, setInstalling] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<{ kind: "ok" | "err"; text: string } | null>(null);
  const [installDir, setInstallDir] = useState<string>("");

  const load = useCallback(async () => {
    try {
      const ckpts = await api.checkpoints();
      setItems(ckpts);
      setError(null);
      // Derive install dir from the first installed/missing entry path base.
      const sample = ckpts.find((c) => c.path);
      if (sample?.path) {
        setInstallDir(sample.path.replace(/[\\/][^\\/]+$/, ""));
      }
    } catch (e) {
      setError(e instanceof ApiClientError ? e.body.message : String(e));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const handleInstall = async (name: string) => {
    setInstalling(name);
    setNote(null);
    try {
      await api.installCheckpoint(name);
      setNote({ kind: "ok", text: t("environment.installedOk") });
      await load();
    } catch (e) {
      setNote({ kind: "err", text: e instanceof ApiClientError ? e.body.message : String(e) });
    } finally {
      setInstalling(null);
    }
  };

  const handleClean = async () => {
    if (!window.confirm(t("environment.cleanConfirm"))) return;
    try {
      await api.cleanCheckpoints();
      setNote({ kind: "ok", text: t("environment.cleanOk") });
      await load();
    } catch (e) {
      setNote({ kind: "err", text: e instanceof ApiClientError ? e.body.message : String(e) });
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-800">{t("environment.title")}</h1>
          <p className="text-sm text-slate-500">{t("environment.subtitle")}</p>
        </div>
        {items && items.some((c) => c.installed) && (
          <button
            className="px-3 py-1.5 border border-red-200 text-red-600 rounded-md text-sm hover:bg-red-50"
            onClick={() => void handleClean()}
          >
            {t("environment.clean")}
          </button>
        )}
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-md px-3 py-2">{error}</div>
      )}
      {note && (
        <div
          className={`text-sm rounded-md px-3 py-2 border ${
            note.kind === "ok"
              ? "bg-green-50 text-green-700 border-green-200"
              : "bg-red-50 text-red-700 border-red-200"
          }`}
        >
          {note.text}
        </div>
      )}
      {installDir && <p className="text-xs text-slate-400">{t("environment.installNote", { dir: installDir })}</p>}

      {items === null ? (
        <p className="text-slate-400 py-10 text-center">{t("common.loading")}</p>
      ) : items.length === 0 ? (
        <p className="text-slate-400 py-10 text-center">{t("environment.noCheckpoints")}</p>
      ) : (
        <div className="bg-white border border-surface-border rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-surface-alt text-left text-xs uppercase text-slate-500">
                <th className="px-4 py-3">{t("environment.col.name")}</th>
                <th className="px-4 py-3">{t("environment.col.filename")}</th>
                <th className="px-4 py-3">{t("environment.col.description")}</th>
                <th className="px-4 py-3">{t("environment.col.size")}</th>
                <th className="px-4 py-3">{t("environment.col.status")}</th>
                <th className="px-4 py-3 text-right">{t("environment.col.actions")}</th>
              </tr>
            </thead>
            <tbody>
              {items.map((c) => (
                <tr key={c.name} className="border-t border-surface-border">
                  <td className="px-4 py-3 font-mono text-xs font-medium text-slate-700">{c.name}</td>
                  <td className="px-4 py-3 font-mono text-xs text-slate-500">{c.filename}</td>
                  <td className="px-4 py-3 text-slate-500 text-xs max-w-xs">{c.description}</td>
                  <td className="px-4 py-3 text-slate-500 text-xs">{formatSize(c.size_bytes, t)}</td>
                  <td className="px-4 py-3">
                    {c.installed ? (
                      <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full">
                        {t("environment.installed")}
                      </span>
                    ) : (
                      <span className="text-xs bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full">
                        {t("environment.missing")}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      disabled={installing !== null}
                      className="text-xs px-3 py-1 border border-surface-border rounded-md hover:bg-surface-alt disabled:opacity-50"
                      onClick={() => void handleInstall(c.name)}
                    >
                      {installing === c.name ? t("environment.installing") : c.installed ? t("environment.reinstall") : t("environment.install")}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
