import React, { useState } from "react";
import {
  AlertTriangle,
  ArrowUpDown,
  CalendarClock,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Filter,
  Info,
  MapPin,
  ShieldCheck,
  Thermometer,
  Wind,
} from "lucide-react";
import { useTripStore } from "../store/useTripStore";
import type {
  AnalyzedRoute,
  DepartureWindowResponse,
  RouteCheckpoint,
} from "../types/api";
import {
  formatDuration,
  RISK_BADGE_CLASSES,
  RISK_COLORS,
  RISK_SHAPES,
} from "../utils/risk";

interface RouteDetailsDrawerProps {
  selectedRoute: AnalyzedRoute | undefined;
  departureWindow: DepartureWindowResponse | undefined;
  isLoadingDepartureWindow: boolean;
  onSelectCheckpoint: (cp: RouteCheckpoint) => void;
}

export const RouteDetailsDrawer: React.FC<RouteDetailsDrawerProps> = ({
  selectedRoute,
  departureWindow,
  isLoadingDepartureWindow,
  onSelectCheckpoint,
}) => {
  const {
    activeDetailTab,
    setActiveDetailTab,
    selectedCheckpoint,
    loadWeightLb,
  } = useTripStore();

  const [filterHighPlus, setFilterHighPlus] = useState(false);
  const [sortBy, setSortBy] = useState<"mile" | "risk" | "wind">("mile");
  const [sortAsc, setSortAsc] = useState(true);
  const [isDrawerExpanded, setIsDrawerExpanded] = useState(true);

  if (!selectedRoute) return null;

  const checkpoints = selectedRoute.checkpoints;
  const totalMiles = Math.max(1, selectedRoute.distanceMi);
  const highOrWorseCount = checkpoints.filter(
    (cp) => cp.score >= 2 || cp.score < 0
  ).length;

  const filteredCheckpoints = checkpoints
    .filter((cp) => (filterHighPlus ? cp.score >= 2 || cp.score < 0 : true))
    .slice()
    .sort((a, b) => {
      let cmp = 0;
      if (sortBy === "mile") cmp = a.mile - b.mile;
      else if (sortBy === "risk") cmp = b.score - a.score || a.mile - b.mile;
      else if (sortBy === "wind")
        cmp = (b.weather.windMph ?? 0) - (a.weather.windMph ?? 0);
      return sortAsc ? cmp : -cmp;
    });

  const toggleSort = (col: "mile" | "risk" | "wind") => {
    if (sortBy === col) {
      setSortAsc(!sortAsc);
    } else {
      setSortBy(col);
      setSortAsc(col === "mile");
    }
  };

  return (
    <div className="bg-slate-900/95 border border-slate-800 rounded-xl p-3.5 shadow-xl space-y-3">
      {/* Risk Profile Strip Under Selected Route (PRD MP-6) */}
      <div>
        <div className="flex flex-wrap items-center justify-between gap-2 text-xs mb-1.5">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-slate-200">
              Route Risk Profile · {selectedRoute.label} (
              {selectedRoute.distanceMi.toFixed(0)} mi)
            </span>
            {highOrWorseCount > 0 ? (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-orange-500/20 text-orange-300 border border-orange-500/40">
                <AlertTriangle className="w-3 h-3" />
                {highOrWorseCount} Hazard Checkpoint
                {highOrWorseCount > 1 ? "s" : ""}
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-500/15 text-emerald-300 border border-emerald-500/40">
                <CheckCircle2 className="w-3 h-3" />0 High/Severe Hazards
              </span>
            )}
          </div>
          <span className="text-[11px] text-slate-400">
            Click any bar segment to inspect on map
          </span>
        </div>

        <div className="h-5 w-full rounded-lg bg-slate-950 border border-slate-800 overflow-hidden flex p-0.5 gap-[1px]">
          {checkpoints.map((cp) => {
            const widthPct = Math.max(
              0.8,
              (cp.segmentMiles / totalMiles) * 100
            );
            const isSelectedCp = selectedCheckpoint?.index === cp.index;
            return (
              <button
                key={cp.index}
                type="button"
                onClick={() => onSelectCheckpoint(cp)}
                style={{
                  width: `${widthPct}%`,
                  backgroundColor: RISK_COLORS[cp.level],
                }}
                title={`Mile ${cp.mile.toFixed(0)} (${cp.place}) · ${
                  cp.etaLocalDisplay
                } · ${cp.level}: ${cp.reasons[0] ?? ""}`}
                className={`h-full transition hover:brightness-125 ${
                  isSelectedCp ? "ring-2 ring-white z-10" : "opacity-90"
                }`}
              />
            );
          })}
        </div>

        <div className="flex justify-between text-[10px] font-mono text-slate-500 mt-1">
          <span>Mile 0 (Origin)</span>
          <span>Mile {(totalMiles * 0.25).toFixed(0)}</span>
          <span>Mile {(totalMiles * 0.5).toFixed(0)}</span>
          <span>Mile {(totalMiles * 0.75).toFixed(0)}</span>
          <span>Mile {totalMiles.toFixed(0)} (Dest)</span>
        </div>
      </div>

      {/* Tabs: Checkpoints Table | Departure Window Finder | Risk & Load Rules + Collapse Toggle */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-2">
        <div className="flex flex-wrap items-center gap-1.5">
          <button
            type="button"
            onClick={() => {
              setActiveDetailTab("checkpoints");
              setIsDrawerExpanded(true);
            }}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition ${
              activeDetailTab === "checkpoints"
                ? "bg-sky-500 text-slate-950 shadow"
                : "bg-slate-800/80 text-slate-300 hover:bg-slate-800"
            }`}
          >
            Checkpoints ({checkpoints.length})
          </button>
          <button
            type="button"
            onClick={() => {
              setActiveDetailTab("departure-window");
              setIsDrawerExpanded(true);
            }}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition flex items-center gap-1.5 ${
              activeDetailTab === "departure-window"
                ? "bg-sky-500 text-slate-950 shadow"
                : "bg-slate-800/80 text-slate-300 hover:bg-slate-800"
            }`}
          >
            <CalendarClock className="w-3.5 h-3.5" />
            Departure Window Finder (±12h)
          </button>
          <button
            type="button"
            onClick={() => {
              setActiveDetailTab("rules");
              setIsDrawerExpanded(true);
            }}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition flex items-center gap-1.5 ${
              activeDetailTab === "rules"
                ? "bg-sky-500 text-slate-950 shadow"
                : "bg-slate-800/80 text-slate-300 hover:bg-slate-800"
            }`}
          >
            <ShieldCheck className="w-3.5 h-3.5" />
            Risk & Load Rules Reference
          </button>
        </div>

        <div className="flex items-center gap-2">
          {activeDetailTab === "checkpoints" && isDrawerExpanded && (
            <button
              type="button"
              onClick={() => setFilterHighPlus(!filterHighPlus)}
              className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs border transition ${
                filterHighPlus
                  ? "bg-orange-500/20 text-orange-300 border-orange-500/50 font-semibold"
                  : "bg-slate-800 text-slate-300 border-slate-700 hover:bg-slate-700"
              }`}
            >
              <Filter className="w-3 h-3" />
              <span>
                {filterHighPlus
                  ? `Showing Hazards (${highOrWorseCount})`
                  : `High & Above Only (${highOrWorseCount})`}
              </span>
            </button>
          )}

          <button
            type="button"
            onClick={() => setIsDrawerExpanded(!isDrawerExpanded)}
            className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs bg-slate-800/80 hover:bg-slate-800 text-slate-300 border border-slate-700 transition"
          >
            <span>{isDrawerExpanded ? "Collapse" : "Expand Table"}</span>
            {isDrawerExpanded ? (
              <ChevronUp className="w-3.5 h-3.5" />
            ) : (
              <ChevronDown className="w-3.5 h-3.5" />
            )}
          </button>
        </div>
      </div>

      {/* Tab 1: Sortable Checkpoints Table (MP-7) */}
      {isDrawerExpanded && activeDetailTab === "checkpoints" && (
        <div className="overflow-x-auto max-h-72 overflow-y-auto rounded-lg border border-slate-800">
          <table className="w-full text-left border-collapse text-xs">
            <thead className="bg-slate-950/90 text-slate-400 uppercase text-[10px] sticky top-0 z-10 border-b border-slate-800">
              <tr>
                <th className="py-2 px-2.5">
                  <button
                    type="button"
                    onClick={() => toggleSort("mile")}
                    className="inline-flex items-center gap-1 hover:text-white font-semibold"
                  >
                    Mile <ArrowUpDown className="w-3 h-3" />
                  </button>
                </th>
                <th className="py-2 px-2.5">Location</th>
                <th className="py-2 px-2.5">Local ETA</th>
                <th className="py-2 px-2.5">
                  <button
                    type="button"
                    onClick={() => toggleSort("wind")}
                    className="inline-flex items-center gap-1 hover:text-white font-semibold"
                  >
                    Wind / Gust <ArrowUpDown className="w-3 h-3" />
                  </button>
                </th>
                <th className="py-2 px-2.5">Rain / Snow</th>
                <th className="py-2 px-2.5">Temp</th>
                <th className="py-2 px-2.5">
                  <button
                    type="button"
                    onClick={() => toggleSort("risk")}
                    className="inline-flex items-center gap-1 hover:text-white font-semibold"
                  >
                    Risk Level <ArrowUpDown className="w-3 h-3" />
                  </button>
                </th>
                <th className="py-2 px-2.5">Classification Reason</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {filteredCheckpoints.length === 0 ? (
                <tr>
                  <td
                    colSpan={8}
                    className="py-6 text-center text-slate-400 text-xs"
                  >
                    No checkpoints at High risk or above on this route.
                  </td>
                </tr>
              ) : (
                filteredCheckpoints.map((cp) => {
                  const isActive = selectedCheckpoint?.index === cp.index;
                  return (
                    <tr
                      key={cp.index}
                      onClick={() => onSelectCheckpoint(cp)}
                      className={`cursor-pointer transition ${
                        isActive
                          ? "bg-sky-500/20 text-white"
                          : "hover:bg-slate-800/60 text-slate-200"
                      }`}
                    >
                      <td className="py-2 px-2.5 font-mono font-semibold whitespace-nowrap">
                        {cp.mile.toFixed(0)} mi
                      </td>
                      <td className="py-2 px-2.5 whitespace-nowrap">
                        <span className="inline-flex items-center gap-1">
                          <MapPin className="w-3 h-3 text-slate-400 shrink-0" />
                          {cp.place}
                        </span>
                      </td>
                      <td className="py-2 px-2.5 font-mono text-[11px] whitespace-nowrap text-slate-300">
                        {cp.etaLocalDisplay}
                        {cp.etaIsEstimate && (
                          <span className="ml-1 text-[10px] text-amber-400">
                            (est)
                          </span>
                        )}
                      </td>
                      <td className="py-2 px-2.5 font-mono whitespace-nowrap">
                        {cp.weather.windMph !== null ? (
                          <span>
                            <strong className="text-slate-100">
                              {cp.weather.windMph.toFixed(1)}
                            </strong>{" "}
                            mph{" "}
                            <span className="text-slate-400 text-[10px]">
                              (g {cp.weather.gustMph?.toFixed(0) ?? "—"})
                            </span>
                          </span>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className="py-2 px-2.5 font-mono whitespace-nowrap">
                        R: {(cp.weather.rainInHr ?? 0).toFixed(2)}&quot; · S:{" "}
                        {(cp.weather.snowInHr ?? 0).toFixed(2)}&quot;
                      </td>
                      <td className="py-2 px-2.5 font-mono whitespace-nowrap">
                        {cp.weather.temperatureF !== null
                          ? `${cp.weather.temperatureF.toFixed(0)}°F`
                          : "—"}
                      </td>
                      <td className="py-2 px-2.5 whitespace-nowrap">
                        <span
                          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded border text-[11px] ${
                            RISK_BADGE_CLASSES[cp.level]
                          }`}
                        >
                          <span>{RISK_SHAPES[cp.level]}</span>
                          <span>{cp.level}</span>
                        </span>
                        {cp.loadEscalated && (
                          <span
                            title="Escalated by Cargo Load Weight Rule"
                            className="ml-1 px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/40 text-[10px] font-semibold"
                          >
                            Load↑
                          </span>
                        )}
                      </td>
                      <td className="py-2 px-2.5 text-slate-300 max-w-xs truncate">
                        {cp.reasons.join(" · ")}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Tab 2: Departure Window Finder (SC-6) */}
      {isDrawerExpanded && activeDetailTab === "departure-window" && (
        <div className="space-y-2.5">
          {isLoadingDepartureWindow ? (
            <div className="py-6 text-center text-xs text-sky-400 animate-pulse">
              Scanning ±12h departure windows against cached 48h corridor
              forecast...
            </div>
          ) : departureWindow ? (
            <>
              <div className="p-3 rounded-lg bg-sky-500/10 border border-sky-500/30 flex items-center justify-between gap-2 text-xs">
                <div className="flex items-center gap-2 text-sky-200">
                  <Info className="w-4 h-4 text-sky-400 shrink-0" />
                  <span>{departureWindow.suggestion}</span>
                </div>
                <span className="font-mono text-[11px] text-sky-300 shrink-0">
                  Best offset:{" "}
                  {departureWindow.recommendedOffsetHours >= 0
                    ? `+${departureWindow.recommendedOffsetHours}h`
                    : `${departureWindow.recommendedOffsetHours}h`}
                </span>
              </div>

              <div className="overflow-x-auto max-h-60 overflow-y-auto rounded-lg border border-slate-800">
                <table className="w-full text-left border-collapse text-xs">
                  <thead className="bg-slate-950 text-slate-400 uppercase text-[10px] sticky top-0">
                    <tr>
                      <th className="py-2 px-2.5">Offset</th>
                      <th className="py-2 px-2.5">Departure (Origin Local)</th>
                      <th className="py-2 px-2.5">Best Route</th>
                      <th className="py-2 px-2.5">Status</th>
                      <th className="py-2 px-2.5">Severe Mi</th>
                      <th className="py-2 px-2.5">High Mi</th>
                      <th className="py-2 px-2.5">Avg Risk</th>
                      <th className="py-2 px-2.5">Duration</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60">
                    {departureWindow.windows.map((w) => {
                      const isBest =
                        w.offsetHours ===
                        departureWindow.recommendedOffsetHours;
                      const isCurrent = w.offsetHours === 0;
                      return (
                        <tr
                          key={w.offsetHours}
                          className={`${
                            isBest
                              ? "bg-emerald-500/15 text-emerald-100"
                              : isCurrent
                              ? "bg-sky-500/10 text-sky-100"
                              : "text-slate-300"
                          }`}
                        >
                          <td className="py-1.5 px-2.5 font-mono font-bold">
                            {w.offsetHours >= 0
                              ? `+${w.offsetHours}h`
                              : `${w.offsetHours}h`}
                            {isCurrent && (
                              <span className="ml-1.5 text-[10px] px-1.5 py-0.5 rounded bg-sky-500/30 text-sky-200">
                                Selected
                              </span>
                            )}
                            {isBest && (
                              <span className="ml-1.5 text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/30 text-emerald-200">
                                Safest
                              </span>
                            )}
                          </td>
                          <td className="py-1.5 px-2.5 font-mono text-[11px]">
                            {w.departureTimeLocal}
                          </td>
                          <td className="py-1.5 px-2.5 font-medium">
                            {w.bestRouteLabel}
                          </td>
                          <td className="py-1.5 px-2.5">
                            {w.allBlocked ? (
                              <span className="text-red-400 font-semibold">
                                Blocked ({w.noTravelMiles.toFixed(0)} mi)
                              </span>
                            ) : (
                              <span className="text-emerald-400 font-semibold">
                                Clear
                              </span>
                            )}
                          </td>
                          <td className="py-1.5 px-2.5 font-mono">
                            {w.severeMiles.toFixed(0)} mi
                          </td>
                          <td className="py-1.5 px-2.5 font-mono">
                            {w.highMiles.toFixed(0)} mi
                          </td>
                          <td className="py-1.5 px-2.5 font-mono">
                            {w.avgRisk.toFixed(2)}
                          </td>
                          <td className="py-1.5 px-2.5 font-mono">
                            {formatDuration(w.durationMin)}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </>
          ) : null}
        </div>
      )}

      {/* Tab 3: Risk & Load Rules Table Reference */}
      {isDrawerExpanded && activeDetailTab === "rules" && (
        <div className="space-y-3 text-xs">
          <div className="overflow-x-auto rounded-lg border border-slate-800">
            <table className="w-full text-left border-collapse">
              <thead className="bg-slate-950 text-slate-400 uppercase text-[10px]">
                <tr>
                  <th className="py-2 px-3">Condition</th>
                  <th className="py-2 px-3 text-emerald-400">● Low (0)</th>
                  <th className="py-2 px-3 text-amber-400">◆ Moderate (1)</th>
                  <th className="py-2 px-3 text-orange-400">▲ High (2)</th>
                  <th className="py-2 px-3 text-red-400">■ Severe (3)</th>
                  <th className="py-2 px-3 text-red-300">✖ No Travel (4)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800 text-slate-200 font-mono text-[11px]">
                <tr>
                  <td className="py-2 px-3 font-sans font-semibold flex items-center gap-1.5">
                    <Wind className="w-3.5 h-3.5 text-sky-400" /> Wind (mph)
                  </td>
                  <td className="py-2 px-3">&lt; 25.0</td>
                  <td className="py-2 px-3">25.0 to &lt; 35.0</td>
                  <td className="py-2 px-3">35.0 to &lt; 45.0</td>
                  <td className="py-2 px-3">45.0 to &lt; 55.0</td>
                  <td className="py-2 px-3">&ge; 55.0</td>
                </tr>
                <tr>
                  <td className="py-2 px-3 font-sans font-semibold">
                    Rain (in/hr)
                  </td>
                  <td className="py-2 px-3">&lt; 0.10</td>
                  <td className="py-2 px-3">0.10 to 0.25</td>
                  <td className="py-2 px-3">&gt; 0.25 to 0.50</td>
                  <td className="py-2 px-3">&gt; 0.50 to 1.00</td>
                  <td className="py-2 px-3">&gt; 1.00</td>
                </tr>
                <tr>
                  <td className="py-2 px-3 font-sans font-semibold flex items-center gap-1.5">
                    <Thermometer className="w-3.5 h-3.5 text-sky-400" /> Snow
                    (in/hr)
                  </td>
                  <td className="py-2 px-3">&lt; 0.5</td>
                  <td className="py-2 px-3">0.5 to 1.0</td>
                  <td className="py-2 px-3">&gt; 1.0 to 2.0</td>
                  <td className="py-2 px-3">&gt; 2.0 to 3.0</td>
                  <td className="py-2 px-3">&gt; 3.0</td>
                </tr>
              </tbody>
            </table>
          </div>

          <div className="p-3 rounded-lg bg-slate-950/90 border border-slate-800 space-y-1 text-slate-300">
            <div className="font-semibold text-slate-100 flex items-center gap-1.5">
              <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
              Active Cargo Load Weight Escalation Rules (Current Load:{" "}
              {Math.round(loadWeightLb).toLocaleString()} lb)
            </div>
            <p>
              • <strong>Rule (a):</strong> Wind &ge; 55 mph is{" "}
              <span className="text-red-300 font-semibold">No Travel</span> for
              any load weight.
            </p>
            <p>
              • <strong>Rule (b):</strong> Wind 45.0 to &lt; 55.0 mph with load
              &gt; 30,000 lb escalates to{" "}
              <span className="text-red-300 font-semibold">No Travel</span>{" "}
              {loadWeightLb > 30000 ? "(ACTIVE)" : "(Inactive at current weight)"}.
            </p>
            <p>
              • <strong>Rule (c):</strong> Wind 35.0 to &lt; 45.0 mph with load
              &gt; 40,000 lb escalates to{" "}
              <span className="text-orange-300 font-semibold">Severe</span>{" "}
              {loadWeightLb > 40000 ? "(ACTIVE)" : "(Inactive at current weight)"}.
            </p>
          </div>
        </div>
      )}
    </div>
  );
};
