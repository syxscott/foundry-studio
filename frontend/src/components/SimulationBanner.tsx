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
    <div className="bg-amber-50 border-b border-amber-200 text-amber-900 text-sm">
      <div className="max-w-6xl mx-auto px-4 py-2 flex items-start gap-2">
        <span aria-hidden>⚠</span>
        <p>{t("app.simulationBanner")}</p>
      </div>
    </div>
  );
}
