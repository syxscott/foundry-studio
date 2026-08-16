import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import * as NGL from "ngl";

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
  const [rep, setRep] = useState<Representation>("cartoon");
  const [color, setColor] = useState<ColorScheme>("chainid");
  const [error, setError] = useState<string | null>(null);

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
        structure.autoView();
        addRepresentation(stage, structure, "cartoon", "chainid");
      })
      .catch((e: unknown) => {
        setError(e instanceof Error ? e.message : String(e));
      });

    return () => {
      stage.dispose();
      stageRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url]);

  const addRepresentation = (
    stage: NGL.Stage,
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
    stage.viewer.requestRender();
  };

  const updateRep = (next: Representation) => {
    setRep(next);
    const stage = stageRef.current;
    const comp = stage?.compList[0] as NGL.StructureComponent | undefined;
    if (stage && comp) addRepresentation(stage, comp, next, color);
  };

  const updateColor = (next: ColorScheme) => {
    setColor(next);
    const stage = stageRef.current;
    const comp = stage?.compList[0] as NGL.StructureComponent | undefined;
    if (stage && comp) addRepresentation(stage, comp, rep, next);
  };

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/60 flex items-center justify-center p-4">
      <div className="bg-white rounded-lg w-full max-w-4xl h-[85vh] flex flex-col">
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
            className="btn-soft"
            onClick={() => {
              stageRef.current?.compList[0]?.autoView();
              stageRef.current?.viewer.requestRender();
            }}
          >
            {t("viewer.reset")}
          </button>
        </div>

        <div className="relative flex-1">
          <div ref={containerRef} className="absolute inset-0" />
          {error && (
            <div className="absolute inset-0 flex items-center justify-center bg-white/80 text-red-600 text-sm">
              {t("viewer.loadFailed", { detail: error })}
            </div>
          )}
          {!error && <div className="absolute top-2 left-2 text-xs text-slate-400">{t("viewer.loading")}</div>}
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
