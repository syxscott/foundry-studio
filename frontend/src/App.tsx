import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "./api";
import { SimulationBanner } from "./components/SimulationBanner";
import { LanguageSwitcher } from "./components/LanguageSwitcher";
import type { HealthResponse } from "./types/api";
import {
  EnvironmentPage,
  HomePage,
  JobDetailPage,
  JobsPage,
} from "./pages";

type Route =
  | { name: "home" }
  | { name: "jobs" }
  | { name: "job"; id: string }
  | { name: "environment" };

function parseHash(): Route {
  const hash = window.location.hash.replace(/^#\/?/, "");
  const parts = hash.split("/").filter(Boolean);
  if (parts[0] === "jobs") {
    if (parts[1]) return { name: "job", id: parts[1] };
    return { name: "jobs" };
  }
  if (parts[0] === "environment") return { name: "environment" };
  return { name: "home" };
}

export default function App() {
  const { t } = useTranslation();
  const [route, setRoute] = useState<Route>(parseHash);
  const [health, setHealth] = useState<HealthResponse | null>(null);

  useEffect(() => {
    const onHash = () => setRoute(parseHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  useEffect(() => {
    let alive = true;
    const load = () => {
      api
        .health()
        .then((h) => alive && setHealth(h))
        .catch(() => alive && setHealth(null));
    };
    load();
    const id = setInterval(load, 15000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  const navigate = (r: Route) => {
    if (r.name === "home") window.location.hash = "#/";
    else if (r.name === "jobs") window.location.hash = "#/jobs";
    else if (r.name === "job") window.location.hash = `#/jobs/${r.id}`;
    else window.location.hash = "#/environment";
  };

  const navClass = (active: boolean) =>
    `px-3 py-2 rounded-md text-sm font-medium transition-colors ${
      active ? "bg-brand-600 text-white" : "text-slate-600 hover:bg-slate-100"
    }`;

  return (
    <div className="min-h-screen flex flex-col">
      <header className="bg-white border-b border-surface-border sticky top-0 z-20">
        <div className="max-w-6xl mx-auto px-4 h-14 flex items-center gap-4">
          <button
            className="flex items-center gap-2 font-semibold text-brand-700"
            onClick={() => navigate({ name: "home" })}
          >
            <span className="text-lg">🧬</span>
            <span>{t("app.title")}</span>
          </button>
          <nav className="flex-1 flex gap-1">
            <button className={navClass(route.name === "home")} onClick={() => navigate({ name: "home" })}>
              {t("app.nav.home")}
            </button>
            <button className={navClass(route.name === "jobs" || route.name === "job")} onClick={() => navigate({ name: "jobs" })}>
              {t("app.nav.jobs")}
            </button>
            <button className={navClass(route.name === "environment")} onClick={() => navigate({ name: "environment" })}>
              {t("app.nav.environment")}
            </button>
          </nav>
          <LanguageSwitcher />
        </div>
      </header>

      <SimulationBanner health={health} />

      <main className="flex-1 max-w-6xl w-full mx-auto px-4 py-6">
        {route.name === "home" && <HomePage health={health} />}
        {route.name === "jobs" && <JobsPage onOpen={(id) => navigate({ name: "job", id })} />}
        {route.name === "job" && (
          <JobDetailPage jobId={route.id} onBack={() => navigate({ name: "jobs" })} />
        )}
        {route.name === "environment" && <EnvironmentPage />}
      </main>

      <footer className="border-t border-surface-border py-4 text-center text-xs text-slate-400">
        {t("app.title")} · {t("app.tagline")}
        {health && <span className="ml-2">· v{health.version}</span>}
      </footer>
    </div>
  );
}
