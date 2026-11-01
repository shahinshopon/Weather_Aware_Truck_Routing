import type { RiskLevelLabel } from "../types/api";

export const RISK_COLORS: Record<RiskLevelLabel, string> = {
  Low: "#10b981", // Emerald 500
  Moderate: "#eab308", // Yellow 500
  High: "#f97316", // Orange 500
  Severe: "#ef4444", // Red 500
  "No Travel": "#991b1b", // Red 800 / Deep Crimson
  Unknown: "#64748b", // Slate 500
};

export const RISK_BADGE_CLASSES: Record<RiskLevelLabel, string> = {
  Low: "bg-emerald-500/15 text-emerald-300 border-emerald-500/40",
  Moderate: "bg-amber-500/15 text-amber-300 border-amber-500/40",
  High: "bg-orange-500/20 text-orange-300 border-orange-500/50",
  Severe: "bg-red-500/20 text-red-300 border-red-500/50",
  "No Travel": "bg-red-900/50 text-red-200 border-red-500/80 font-bold",
  Unknown: "bg-slate-600/20 text-slate-300 border-slate-500/40",
};

/**
 * Distinct non-color shape codes per risk level (PRD MP-3 & UX-5 Accessibility):
 * - Low: Circle (●)
 * - Moderate: Diamond (◆)
 * - High: Triangle (▲)
 * - Severe: Square (■)
 * - No Travel: Octagon / Stop (✖)
 * - Unknown: Question (?)
 */
export const RISK_SHAPES: Record<RiskLevelLabel, string> = {
  Low: "●",
  Moderate: "◆",
  High: "▲",
  Severe: "■",
  "No Travel": "✖",
  Unknown: "?",
};

export function formatDuration(minutes: number): string {
  if (!Number.isFinite(minutes) || minutes <= 0) return "0m";
  const hrs = Math.floor(minutes / 60);
  const mins = Math.round(minutes % 60);
  if (hrs === 0) return `${mins}m`;
  if (mins === 0) return `${hrs}h`;
  return `${hrs}h ${mins}m`;
}

export function getNextQuarterHourLocalIso(): string {
  const now = new Date();
  const ms = 1000 * 60 * 15;
  const rounded = new Date(Math.ceil(now.getTime() / ms) * ms);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${rounded.getFullYear()}-${pad(rounded.getMonth() + 1)}-${pad(
    rounded.getDate()
  )}T${pad(rounded.getHours())}:${pad(rounded.getMinutes())}`;
}

export const SAMPLE_TRIPS = [
  {
    id: "chicago-denver",
    name: "Chicago, IL → Denver, CO",
    subtitle: "I-80 / I-76 / I-70 Great Plains Corridor (~1,005 mi)",
    origin: { label: "Chicago, IL", lat: 41.8781, lng: -87.6298 },
    destination: { label: "Denver, CO", lat: 39.7392, lng: -104.9903 },
    loadWeightLb: 35000,
    intervalMiles: 25 as const,
  },
  {
    id: "dallas-okc",
    name: "Dallas, TX → Oklahoma City, OK",
    subtitle: "I-35 / US-287 / US-75 Red River Corridor (~206 mi)",
    origin: { label: "Dallas, TX", lat: 32.7767, lng: -96.797 },
    destination: { label: "Oklahoma City, OK", lat: 35.4676, lng: -97.5164 },
    loadWeightLb: 45000,
    intervalMiles: 25 as const,
  },
];

export const LOAD_PRESETS_LB = [20000, 35000, 45000, 80000] as const;
