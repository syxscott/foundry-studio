import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import * as NGL from "ngl";

import { toast } from "./Toaster";

type Representation =
  | "cartoon"
  | "ball+stick"
  | "surface"
  | "spacefill"
  | "ribbon";

type ColorScheme =
  | "chainid"
  | "secondary_structure"
  | "residueindex"
  | "bfactor";
const REPS: Representation[] = ["cartoon", "ball+stick", "surface", "spacefill", "ribbon"];
const COLORS: { value: ColorScheme; key: string }[] = [
  { value: "chainid", key: "viewer.colorChain" },
  { value: "secondary_structure", key: "viewer.colorSecondary" },
  { value: "residueindex", key: "viewer.colorResidue" },
  { value: "bfactor", key: "viewer.colorBFactor" },
];

export function StructureViewer({
  url,
  onClose,
}: {
  url: string;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const containerRef = useRef<HTMLDivElement>(null);
  const stageRef = useRef<NGL.Stage | null>(null);
  const componentRef = useRef<NGL.StructureComponent | null>(null);
  const [rep, setRep] = useState<Representation>("cartoon");
  const [color, setColor] = useState<ColorScheme>("chainid");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [autoSpin, setAutoSpin] = useState(false);
  // Persistent render loop state; the stage is mutated by the spin hook below.
  const spinHandleRef = useRef<{ tick: () => void; stop: () => void } | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const stage = new NGL.Stage(containerRef.current, {
      backgroundColor: "#ffffff",
    });
    stageRef.current = stage;

    stage
      .loadFile(url, { ext: "cif" })
      .then((component) => {
        const structure = component as NGL.StructureComponent;
        componentRef.current = structure;
        structure.autoView();
        addRepresentation(structure, "cartoon", "chainid");
        setLoading(false);
      })
      .catch((e: unknown) => {
        setError(e instanceof Error ? e.message : String(e));
        setLoading(false);
      });

    return () => {
      if (spinHandleRef.current) {
        spinHandleRef.current.stop();
        spinHandleRef.current = null;
      }
      stage.dispose();
      stageRef.current = null;
      componentRef.current = null;
    };
  }, [url]);

  // ESC closes the viewer.  Bound on mount; we deliberately use a native
  // listener (not a React effect on every render) so it stays attached
  // across the viewer's lifetime regardless of internal state changes.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // Start / stop the auto-spin animation based on the toggle.  NGL exposes
  // a built-in `setSpin(boolean)` so we just delegate to it instead of
  // mutating the camera ourselves.
  useEffect(() => {
    const stage = stageRef.current;
    if (!stage) return;
    if (autoSpin) {
      stage.setSpin(true);
      spinHandleRef.current = {
        tick: () => stage.viewer.requestRender(),
        stop: () => stage.setSpin(false),
      };
    } else {
      stage.setSpin(false);
      spinHandleRef.current = null;
    }
  }, [autoSpin]);

  const addRepresentation = (
    component: NGL.StructureComponent,
    repType: Representation,
    colorScheme: ColorScheme,
  ) => {
    component.removeAllRepresentations();
    component.addRepresentation(repType, {
      colorScheme,
      surfaceType: "av",
    });
    component.autoView();
    const stage = stageRef.current;
    if (stage) stage.viewer.requestRender();
  };

  const updateRep = (next: Representation) => {
    setRep(next);
    if (componentRef.current) addRepresentation(componentRef.current, next, color);
  };

  const updateColor = (next: ColorScheme) => {
    setColor(next);
    if (componentRef.current) addRepresentation(componentRef.current, rep, next);
  };

  const resetView = () => {
    componentRef.current?.autoView();
    stageRef.current?.viewer.requestRender();
  };

  /** Export the current view as a PNG.  NGL renders into a canvas we
   *  can read via `viewer.renderer.domElement.toDataURL`.  We trigger
   *  a render first so the latest state is on the canvas. */
  const takeScreenshot = () => {
    const stage = stageRef.current;
    if (!stage) return;
    stage.viewer.requestRender();
    // Allow the render to flush before reading the canvas.
    requestAnimationFrame(() => {
      try {
        const canvas = (stage.viewer.renderer as { domElement: HTMLCanvasElement }).domElement;
        const dataUrl = canvas.toDataURL("image/png");
        const a = document.createElement("a");
        a.href = dataUrl;
        const ts = new Date().toISOString().replace(/[:.]/g, "-");
        a.download = `structure-${ts}.png`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        toast.success(t("viewer.screenshotSaved"));
      } catch (e) {
        toast.error(t("viewer.screenshotFailed"), String(e));
      }
    });
  };

  return (
    <div
      className="fixed inset-0 z-50 bg-slate-900/60 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
    >
      <div className="bg-white rounded-lg w-full max-w-4xl h-[85vh] flex flex-col animate-fade-in-up">
        <div className="flex items-center justify-between px-4 py-3 border-b border-surface-border">
          <h3 className="font-semibold text-slate-800">{t("viewer.title")}</h3>
          <button className="btn-soft" onClick={onClose}>
            {t("viewer.close")}
          </button>
        </div>

        <div className="flex items-center gap-4 px-4 py-2 border-b border-surface-border flex-wrap">
          <label className="text-xs text-slate-500">
            {t("viewer.representation")}:
            <select
              value={rep}
              onChange={(e) => updateRep(e.target.value as Representation)}
              className="ml-2 border border-surface-border rounded-md px-2 py-1 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-brand-500/30"
            >
              {REPS.map((r) => (
                <option key={r} value={r}>
                  {t(`viewer.rep${repLabel(r)}`)}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs text-slate-500">
            {t("viewer.color")}:
            <select
              value={color}
              onChange={(e) => updateColor(e.target.value as ColorScheme)}
              className="ml-2 border border-surface-border rounded-md px-2 py-1 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-brand-500/30"
            >
              {COLORS.map((c) => (
                <option key={c.value} value={c.value}>
                  {t(c.key)}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="btn-soft"
            onClick={resetView}
            title={t("viewer.resetHint") ?? ""}
          >
            {t("viewer.reset")}
          </button>
          <button
            type="button"
            className={`btn-soft ${autoSpin ? "bg-brand-100 text-brand-700" : ""}`}
            onClick={() => setAutoSpin((s) => !s)}
            aria-pressed={autoSpin}
            title={t("viewer.spinHint") ?? ""}
          >
            {autoSpin ? t("viewer.spinStop") : t("viewer.spinStart")}
          </button>
          <button
            type="button"
            className="btn-soft"
            onClick={takeScreenshot}
            disabled={loading || !!error}
            title={t("viewer.screenshotHint") ?? ""}
          >
            {t("viewer.screenshot")}
          </button>
          <span className="ml-auto text-[11px] text-slate-400 hidden md:inline">
            {t("viewer.shortcutsHint")}
          </span>
        </div>

        <div className="relative flex-1">
          <div ref={containerRef} className="absolute inset-0" />
          {loading && !error && (
            <div className="absolute inset-0 flex items-center justify-center bg-white/70">
              <div className="flex items-center gap-2 text-sm text-slate-500">
                <span className="spinner text-brand-500" />
                {t("viewer.loading")}
              </div>
            </div>
          )}
          {error && (
            <div className="absolute inset-0 flex items-center justify-center bg-white/80 text-red-600 text-sm">
              {t("viewer.loadFailed", { detail: error })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function repLabel(r: Representation): string {
  switch (r) {
    case "cartoon":
      return "Cartoon";
    case "ball+stick":
      return "BallStick";
    case "surface":
      return "Surface";
    case "spacefill":
      return "Spacefill";
    case "ribbon":
      return "Ribbon";
  }
}
