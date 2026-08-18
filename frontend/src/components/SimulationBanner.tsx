import { useTranslation } from "react-i18next";
import type { HealthResponse } from "../types/api";

export function SimulationBanner({ health }: { health: HealthResponse | null }) {
  const { t } = useTranslation();
  if (!health) return null;

  const simulationActive =
    health.engine_mode === "simulation" ||
    (health.engine_mode === "auto" && !health.foundry_available && health.simulation_fallback);

  if (!simulationActive) return null;

  return (
    <div className="bg-amber-50/80 dark:bg-amber-900/50 backdrop-blur border-b border-amber-200 text-amber-900 dark:text-amber-200 text-sm">
      <div className="max-w-6xl mx-auto px-4 py-2 flex items-start gap-2">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="mt-0.5 shrink-0" aria-hidden>
          <path d="M12 9v4m0 4h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" strokeLinejoin="round" />
        </svg>
        <p>{t("app.simulationBanner")}</p>
      </div>
    </div>
  );
}
