import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "./api";
import BackendStatus from "./components/BackendStatus";
import { SimulationBanner } from "./components/SimulationBanner";
import { LanguageSwitcher } from "./components/LanguageSwitcher";
import { Toaster } from "./components/Toaster";
import type { HealthResponse } from "./types/api";
import {
  EnvironmentPage,
  HomePage,
  JobDetailPage,
  JobsPage,
  DesignSessionPage,
  SettingsPage,
} from "./pages";

type Route =
  | { name: "home" }
  | { name: "jobs" }
  | { name: "job"; id: string }
  | { name: "environment" }
  | { name: "settings" }
  | { name: "design"; id?: string };

function parseHash(): Route {
  const hash = window.location.hash.replace(/^#\/?/, "");
  const parts = hash.split("/").filter(Boolean);
  if (parts[0] === "jobs") {
    if (parts[1]) return { name: "job", id: parts[1] };
    return { name: "jobs" };
  }
  if (parts[0] === "environment") return { name: "environment" };
  if (parts[0] === "settings") return { name: "settings" };
  if (parts[0] === "design") {
    if (parts[1]) return { name: "design", id: parts[1] };
    return { name: "design" };
  }
  return { name: "home" };
}

/** Inline double-helix mark — crisp at any size, no emoji dependency. */
function Logo() {
  return (
    <svg width="22" height="22" viewBox="0 0 32 32" fill="none" aria-hidden>
      <rect width="32" height="32" rx="7" fill="url(#fs-grad)" />
      <defs>
        <linearGradient id="fs-grad" x1="0" y1="0" x2="32" y2="32" gradientUnits="userSpaceOnUse">
          <stop stopColor="#225a94" />
          <stop offset="1" stopColor="#0891b2" />
        </linearGradient>
      </defs>
      <g fill="none" strokeLinecap="round" strokeWidth="2">
        <path d="M11 5c5 4 5 8 0 12s-5 8 0 12" stroke="#67e8f9" />
        <path d="M21 5c-5 4-5 8 0 12s5 8 0 12" stroke="#ffffff" />
      </g>
      <g stroke="#cffafe" strokeWidth="1.6">
        <path d="M11 8.5h9M11 14.5h10M11 20.5h9M11 26.5h10" />
      </g>
    </svg>
  );
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
    else if (r.name === "environment") window.location.hash = "#/environment";
    else if (r.name === "settings") window.location.hash = "#/settings";
    else if (r.name === "design") window.location.hash = r.id ? `#/design/${r.id}` : "#/design";
  };

  const navClass = (active: boolean) =>
    `px-3 py-1.5 rounded-full text-sm font-medium transition-colors ${
      active ? "bg-brand-600 text-white shadow-sm" : "text-slate-600 hover:bg-slate-100"
    }`;

  return (
    <div className="min-h-screen flex flex-col">
      <header className="bg-white/90 backdrop-blur border-b border-surface-border sticky top-0 z-20">
        <div className="max-w-6xl mx-auto px-4 h-14 flex items-center gap-4">
          <button
            className="flex items-center gap-2 font-semibold text-slate-800"
            onClick={() => navigate({ name: "home" })}
          >
            <Logo />
            <span className="bg-gradient-to-r from-brand-600 to-accent-500 bg-clip-text text-transparent">
              {t("app.title")}
            </span>
          </button>
          <nav className="flex-1 flex gap-1">
            <button className={navClass(route.name === "home")} onClick={() => navigate({ name: "home" })}>
              {t("app.nav.home")}
            </button>
            <button className={navClass(route.name === "jobs" || route.name === "job")} onClick={() => navigate({ name: "jobs" })}>
              {t("app.nav.jobs")}
            </button>
            <button className={navClass(route.name === "design")} onClick={() => navigate({ name: "design" })}>
              {t("designSession.navButton")}
            </button>
            <button className={navClass(route.name === "environment")} onClick={() => navigate({ name: "environment" })}>
              {t("app.nav.environment")}
            </button>
            <button className={navClass(route.name === "settings")} onClick={() => navigate({ name: "settings" })}>
              {t("app.nav.settings")}
            </button>
          </nav>
          <LanguageSwitcher />
          <span className="ml-1 hidden sm:inline-flex">
            <BackendStatus info={health?.backend ?? null} llm={health?.llm?.providers} />
          </span>
        </div>
      </header>

      <SimulationBanner health={health} />

      <main className="flex-1 max-w-6xl w-full mx-auto px-4 py-6 animate-fade-in">
        {route.name === "home" && <HomePage health={health} onOpenJob={(id) => navigate({ name: "job", id })} />}
        {route.name === "jobs" && <JobsPage onOpen={(id) => navigate({ name: "job", id })} />}
        {route.name === "job" && (
          <JobDetailPage jobId={route.id} onBack={() => navigate({ name: "jobs" })} />
        )}
        {route.name === "environment" && <EnvironmentPage />}
        {route.name === "settings" && <SettingsPage />}
        {route.name === "design" && (
          <DesignSessionPage sessionId={route.id ?? null} />
        )}
      </main>

      <footer className="border-t border-surface-border py-5 text-center text-xs text-slate-400 bg-white/60">
        <p>
          <span className="font-medium text-slate-500">{t("app.title")}</span> · {t("app.tagline")}
          {health && <span className="ml-2 text-slate-300">v{health.version}</span>}
        </p>
      </footer>

      <Toaster />
    </div>
  );
}
