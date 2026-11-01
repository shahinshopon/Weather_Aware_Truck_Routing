import React, { useCallback, useEffect, useState } from "react";
import { useTripStore } from "./store/useTripStore";
import {
  fetchCorridorHeatmap,
  fetchDepartureWindow,
  postAnalyzeTrip,
} from "./api/client";
import type {
  AnalysisResponse,
  DepartureWindowResponse,
  HeatmapResponse,
} from "./types/api";
import { TripInputPanel } from "./components/TripInputPanel";
import { RecommendationBanner, RouteCardsList } from "./components/RouteCards";
import { CorridorMap } from "./components/CorridorMap";
import { HeatmapTimelineBar } from "./components/HeatmapTimelineBar";
import { RouteDetailsDrawer } from "./components/RouteDetailsDrawer";
import { Truck, AlertOctagon, Share2, Check } from "lucide-react";

export const App: React.FC = () => {
  const {
    origin,
    destination,
    loadWeightLb,
    intervalMiles,
    gustAware,
    demoStormMode,
    selectedRouteId,
    setSelectedRouteId,
    setHoveredRouteId,
    setSelectedCheckpoint,
  } = useTripStore();

  const [analysis, setAnalysis] = useState<AnalysisResponse | undefined>(
    undefined
  );
  const [heatmap, setHeatmap] = useState<HeatmapResponse | undefined>(
    undefined
  );
  const [departureWindow, setDepartureWindow] = useState<
    DepartureWindowResponse | undefined
  >(undefined);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [loadingStage, setLoadingStage] = useState<string>("");
  const [isLoadingHeatmap, setIsLoadingHeatmap] = useState<boolean>(false);
  const [isLoadingDepartureWindow, setIsLoadingDepartureWindow] =
    useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [copiedUrl, setCopiedUrl] = useState<boolean>(false);

  const runAnalysis = useCallback(async () => {
    const state = useTripStore.getState();
    setIsLoading(true);
    setLoadingStage("Computing 3 distinct routes & checkpoint ETAs...");
    setErrorMsg(null);
    setDepartureWindow(undefined);

    try {
      const result = await postAnalyzeTrip({
        origin: state.origin,
        destination: state.destination,
        departureTime: new Date(state.departureTimeLocal).toISOString(),
        loadWeightLb: state.loadWeightLb,
        intervalMiles: state.intervalMiles,
        options: {
          gustAware: state.gustAware,
          demoScenario: state.demoStormMode ? "storm" : null,
        },
      });

      setAnalysis(result);
      setSelectedRouteId(
        result.recommendedRouteId ??
          result.leastBadRouteId ??
          result.routes[0]?.id ??
          null
      );

      // Sync URL query params for shareable dispatcher link (IN-5)
      const params = new URLSearchParams();
      params.set("origin", state.origin.label);
      params.set("dest", state.destination.label);
      params.set("weight", String(Math.round(state.loadWeightLb)));
      params.set("interval", String(state.intervalMiles));
      params.set("demo", state.demoStormMode ? "storm" : "0");
      window.history.replaceState(
        {},
        "",
        `${window.location.pathname}?${params.toString()}`
      );

      // Fetch 0-48h corridor heatmap grid once per analysis (HM-1, HM-6)
      setIsLoadingHeatmap(true);
      fetchCorridorHeatmap(result.analysisId)
        .then((hm) => setHeatmap(hm))
        .catch((err) => console.warn("Corridor heatmap warning:", err))
        .finally(() => setIsLoadingHeatmap(false));

      // Pre-fetch ±12h departure window comparison (SC-6)
      setIsLoadingDepartureWindow(true);
      fetchDepartureWindow(result.analysisId)
        .then((dw) => setDepartureWindow(dw))
        .catch((err) => console.warn("Departure window warning:", err))
        .finally(() => setIsLoadingDepartureWindow(false));
    } catch (err: unknown) {
      const message =
        err instanceof Error
          ? err.message
          : "Failed to analyze routes. Please check your inputs.";
      setErrorMsg(message);
    } finally {
      setIsLoading(false);
      setLoadingStage("");
    }
  }, [setSelectedRouteId]);

  // Run initial preloaded sample trip on mount so dispatcher sees routes & heatmap immediately
  useEffect(() => {
    runAnalysis();
  }, [runAnalysis]);

  const handleCopyShareLink = () => {
    navigator.clipboard?.writeText(window.location.href);
    setCopiedUrl(true);
    setTimeout(() => setCopiedUrl(false), 2000);
  };

  const selectedRoute =
    analysis?.routes.find((r) => r.id === selectedRouteId) ??
    analysis?.routes[0];

  return (
    <div className="min-h-screen flex flex-col bg-slate-950 text-slate-100">
      {/* Top Dispatch Header Bar */}
      <header className="h-14 shrink-0 bg-slate-900 border-b border-slate-800 px-4 flex items-center justify-between gap-4 sticky top-0 z-30">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-sky-500/20 border border-sky-400/50 flex items-center justify-center text-sky-400 shadow-inner">
            <Truck className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-sm sm:text-base font-extrabold tracking-tight text-white">
                Weather-Aware Truck Routing
              </h1>
              <span className="hidden md:inline-flex items-center px-2 py-0.5 rounded text-[10px] font-mono font-semibold bg-slate-800 text-sky-300 border border-slate-700">
                48h Corridor Risk & Dispatch
              </span>
            </div>
            <p className="text-[11px] text-slate-400 hidden sm:block">
              Multi-route weather risk evaluation, cargo load escalation & GPU
              corridor heatmap
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 text-xs">
          <span className="hidden lg:inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-slate-950 border border-slate-800 text-slate-300 font-mono">
            <span>{origin.label}</span>
            <span className="text-sky-400">→</span>
            <span>{destination.label}</span>
            <span className="text-slate-500">|</span>
            <span>{Math.round(loadWeightLb).toLocaleString()} lb</span>
            <span className="text-slate-500">|</span>
            <span>{intervalMiles} mi</span>
            {gustAware && <span className="text-amber-300">| Gust-Aware</span>}
            {demoStormMode && <span className="text-amber-400">| Storm Demo</span>}
          </span>

          <button
            type="button"
            onClick={handleCopyShareLink}
            className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition"
            title="Copy shareable trip URL"
          >
            {copiedUrl ? (
              <Check className="w-3.5 h-3.5 text-emerald-400" />
            ) : (
              <Share2 className="w-3.5 h-3.5" />
            )}
            <span className="hidden sm:inline">
              {copiedUrl ? "Copied URL" : "Share Trip"}
            </span>
          </button>
        </div>
      </header>

      {/* Main Responsive Split View: Left Column (Trip Form + Recommendation + 3 Route Cards) & Right Column (Map + 0-48h Timeline + Details Drawer) */}
      <div className="flex-1 grid grid-cols-1 lg:grid-cols-12 gap-4 p-4 max-w-[1920px] w-full mx-auto">
        {/* Left Sidebar Column (5 cols on lg, 4 cols on xl) */}
        <aside className="lg:col-span-5 xl:col-span-4 space-y-4">
          <TripInputPanel
            onSubmit={runAnalysis}
            isLoading={isLoading}
            loadingStage={loadingStage}
          />

          {errorMsg && (
            <div className="p-3.5 rounded-xl bg-red-950/80 border border-red-500/60 text-red-200 text-xs flex items-start gap-2.5">
              <AlertOctagon className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
              <div>
                <div className="font-bold">Route Analysis Error</div>
                <div>{errorMsg}</div>
              </div>
            </div>
          )}

          {analysis && (
            <>
              <RecommendationBanner
                recommendation={analysis.recommendation}
                warnings={analysis.warnings}
                forecastSource={analysis.forecastSource}
                forecastIssuedAt={analysis.forecastIssuedAt}
              />

              <RouteCardsList
                routes={analysis.routes}
                selectedRouteId={selectedRoute?.id ?? null}
                leastBadRouteId={analysis.leastBadRouteId}
                onSelectRoute={(id) => setSelectedRouteId(id)}
                onHoverRoute={(id) => setHoveredRouteId(id)}
              />
            </>
          )}
        </aside>

        {/* Right Workspace Column (7 cols on lg, 8 cols on xl): Map + 0-48h Timeline + Details Drawer */}
        <main className="lg:col-span-7 xl:col-span-8 flex flex-col gap-4">
          <div className="h-[480px] lg:h-[540px] w-full">
            <CorridorMap analysis={analysis} heatmap={heatmap} />
          </div>

          <HeatmapTimelineBar
            heatmap={heatmap}
            isLoadingHeatmap={isLoadingHeatmap}
            selectedRoute={selectedRoute}
          />

          <RouteDetailsDrawer
            selectedRoute={selectedRoute}
            departureWindow={departureWindow}
            isLoadingDepartureWindow={isLoadingDepartureWindow}
            onSelectCheckpoint={(cp) => setSelectedCheckpoint(cp)}
          />
        </main>
      </div>
    </div>
  );
};

export default App;
