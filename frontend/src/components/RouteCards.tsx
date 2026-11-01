import React from "react";
import {
  AlertOctagon,
  AlertTriangle,
  Award,
  CheckCircle2,
  Clock,
  Route,
  ShieldAlert,
} from "lucide-react";
import type {
  AnalyzedRoute,
  RecommendationInfo,
  RiskLevelLabel,
} from "../types/api";
import {
  formatDuration,
  RISK_BADGE_CLASSES,
  RISK_COLORS,
  RISK_SHAPES,
} from "../utils/risk";

interface RecommendationBannerProps {
  recommendation: RecommendationInfo;
  warnings: string[];
  forecastSource: string;
  forecastIssuedAt: string;
}

export const RecommendationBanner: React.FC<RecommendationBannerProps> = ({
  recommendation,
  warnings,
  forecastSource,
  forecastIssuedAt,
}) => {
  const isAllBlocked = recommendation.allBlocked;

  return (
    <div className="space-y-2">
      <div
        className={`rounded-xl border p-3.5 shadow-lg ${
          isAllBlocked
            ? "bg-red-950/50 border-red-500/60 text-red-100"
            : "bg-emerald-950/40 border-emerald-500/50 text-emerald-100"
        }`}
      >
        <div className="flex items-start gap-2.5">
          {isAllBlocked ? (
            <AlertOctagon className="w-5 h-5 text-red-400 shrink-0 mt-0.5" />
          ) : (
            <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0 mt-0.5" />
          )}
          <div className="flex-1 min-w-0">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-sm font-bold tracking-tight">
                {recommendation.headline}
              </h2>
              <span className="text-[10px] font-mono text-slate-400 bg-slate-900/70 px-2 py-0.5 rounded border border-slate-700/60">
                {forecastSource} · Issued {forecastIssuedAt.slice(0, 16)}Z
              </span>
            </div>
            <p className="text-xs mt-1 leading-relaxed text-slate-200">
              {recommendation.explanation}
            </p>
            {recommendation.reasons.length > 1 && (
              <ul className="mt-2 space-y-0.5 text-[11px] text-slate-300 list-disc list-inside">
                {recommendation.reasons.slice(1).map((r, idx) => (
                  <li key={idx}>{r}</li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>

      {warnings.length > 0 && (
        <div className="rounded-lg bg-amber-500/10 border border-amber-500/30 px-3 py-2 text-xs text-amber-200 space-y-1">
          {warnings.map((w, i) => (
            <div key={i} className="flex items-center gap-1.5">
              <AlertTriangle className="w-3.5 h-3.5 text-amber-400 shrink-0" />
              <span>{w}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

interface RouteCardsListProps {
  routes: AnalyzedRoute[];
  selectedRouteId: string | null;
  leastBadRouteId: string | null;
  onSelectRoute: (id: string) => void;
  onHoverRoute: (id: string | null) => void;
}

const ORDERED_LEVELS: RiskLevelLabel[] = [
  "Low",
  "Moderate",
  "High",
  "Severe",
  "No Travel",
  "Unknown",
];

export const RouteCardsList: React.FC<RouteCardsListProps> = ({
  routes,
  selectedRouteId,
  leastBadRouteId,
  onSelectRoute,
  onHoverRoute,
}) => {
  return (
    <div className="space-y-2.5">
      {routes.map((route) => {
        const isSelected = route.id === selectedRouteId;
        const isLeastBad =
          route.blocked &&
          !route.recommended &&
          route.id === leastBadRouteId &&
          routes.every((r) => r.blocked);
        const m = route.metrics;
        const total = Math.max(1, m.totalMiles);

        return (
          <div
            key={route.id}
            role="button"
            tabIndex={0}
            aria-pressed={isSelected}
            onClick={() => onSelectRoute(route.id)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onSelectRoute(route.id);
              }
            }}
            onMouseEnter={() => onHoverRoute(route.id)}
            onMouseLeave={() => onHoverRoute(null)}
            className={`rounded-xl border p-3.5 transition cursor-pointer text-left ${
              isSelected
                ? "bg-slate-900 border-sky-400 ring-2 ring-sky-500/30 shadow-lg"
                : "bg-slate-900/75 border-slate-800 hover:border-slate-700 hover:bg-slate-900"
            }`}
          >
            {/* Card Header: Label + Badges */}
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2 min-w-0">
                <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-slate-800 text-xs font-bold text-slate-200 border border-slate-700">
                  #{route.rank}
                </span>
                <div className="min-w-0">
                  <div className="text-sm font-bold text-slate-100 truncate">
                    {route.label}
                  </div>
                  <div className="text-xs text-slate-400 truncate flex items-center gap-1">
                    <Route className="w-3 h-3 text-sky-400 shrink-0" />
                    <span>{route.summary}</span>
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-1.5 flex-wrap">
                {route.recommended && (
                  <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/50">
                    <Award className="w-3.5 h-3.5" />
                    Recommended
                  </span>
                )}
                {isLeastBad && (
                  <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-amber-500/20 text-amber-200 border border-amber-500/50">
                    Least-Bad Option
                  </span>
                )}
                {route.blocked && (
                  <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-red-900/60 text-red-200 border border-red-500/70">
                    <ShieldAlert className="w-3.5 h-3.5 text-red-400" />
                    Blocked
                  </span>
                )}
                <span
                  className={`px-2 py-0.5 rounded border text-[11px] ${
                    RISK_BADGE_CLASSES[m.maxLevel]
                  }`}
                >
                  {RISK_SHAPES[m.maxLevel]} Max: {m.maxLevel}
                </span>
              </div>
            </div>

            {/* Distance, Duration, Arrival & Avg Risk */}
            <div className="grid grid-cols-4 gap-2 mt-3 pt-2.5 border-t border-slate-800/80 text-xs">
              <div>
                <div className="text-[10px] uppercase text-slate-400">
                  Distance
                </div>
                <div className="font-mono font-semibold text-slate-100">
                  {route.distanceMi.toFixed(0)} mi
                </div>
              </div>
              <div>
                <div className="text-[10px] uppercase text-slate-400">
                  Duration
                </div>
                <div className="font-mono font-semibold text-slate-100 flex items-center gap-1">
                  <Clock className="w-3 h-3 text-slate-400" />
                  {formatDuration(route.durationMin)}
                </div>
              </div>
              <div>
                <div className="text-[10px] uppercase text-slate-400">
                  Avg Risk
                </div>
                <div className="font-mono font-semibold text-slate-100">
                  {m.avgRisk.toFixed(2)}{" "}
                  <span className="text-[10px] text-slate-500">/ 4.0</span>
                </div>
              </div>
              <div>
                <div className="text-[10px] uppercase text-slate-400">
                  ETA (Local)
                </div>
                <div
                  className="font-medium text-slate-200 truncate"
                  title={route.arrivalTimeLocal}
                >
                  {route.arrivalTimeLocal.replace(/^[A-Za-z]+ \d+, /, "")}
                </div>
              </div>
            </div>

            {/* Stacked Risk Mileage Bar (MP-5) */}
            <div className="mt-3 space-y-1.5">
              <div className="h-2.5 w-full rounded-full bg-slate-800 overflow-hidden flex">
                {ORDERED_LEVELS.map((lvl) => {
                  const miles = m.milesByLevel[lvl] ?? 0;
                  if (miles <= 0) return null;
                  const pct = Math.max(1.5, (miles / total) * 100);
                  return (
                    <div
                      key={lvl}
                      style={{
                        width: `${pct}%`,
                        backgroundColor: RISK_COLORS[lvl],
                      }}
                      title={`${lvl}: ${miles.toFixed(1)} mi`}
                    />
                  );
                })}
              </div>

              {/* Mileage Breakdown Pills */}
              <div className="flex flex-wrap items-center justify-between gap-1 text-[11px] text-slate-300">
                <div className="flex flex-wrap items-center gap-2">
                  {ORDERED_LEVELS.map((lvl) => {
                    const miles = m.milesByLevel[lvl] ?? 0;
                    if (miles <= 0) return null;
                    return (
                      <span
                        key={lvl}
                        className="inline-flex items-center gap-1 font-mono"
                      >
                        <span
                          style={{ color: RISK_COLORS[lvl] }}
                          className="text-xs leading-none"
                        >
                          {RISK_SHAPES[lvl]}
                        </span>
                        <span>
                          {lvl}: <strong>{miles.toFixed(0)}</strong> mi
                        </span>
                      </span>
                    );
                  })}
                </div>
              </div>
            </div>

            {/* Tradeoff vs Fastest & Worst Checkpoint Reason */}
            <div className="mt-2.5 pt-2 border-t border-slate-800/60 flex flex-col sm:flex-row sm:items-center justify-between gap-1 text-[11px]">
              <span className="text-sky-300 font-medium">
                {route.tradeoff.summary}
              </span>
              <span className="text-slate-400 truncate">
                Peak: Mile {m.worstCheckpoint.mile.toFixed(0)} (
                {m.worstCheckpoint.place})
              </span>
            </div>

            {route.blocked && route.blockedReason && (
              <div className="mt-2 px-2.5 py-1.5 rounded-lg bg-red-950/60 border border-red-500/40 text-[11px] text-red-200">
                {route.blockedReason}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
};
