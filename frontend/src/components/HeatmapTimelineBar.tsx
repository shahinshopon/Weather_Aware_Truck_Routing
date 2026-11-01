import React, { useEffect } from "react";
import {
  ChevronLeft,
  ChevronRight,
  CloudRain,
  Eye,
  EyeOff,
  Flame,
  Pause,
  Play,
  Snowflake,
  Truck,
  Wind,
} from "lucide-react";
import { useTripStore } from "../store/useTripStore";
import type {
  AnalyzedRoute,
  HeatmapLayerMode,
  HeatmapResponse,
} from "../types/api";
import { RISK_BADGE_CLASSES, RISK_SHAPES } from "../utils/risk";

interface HeatmapTimelineBarProps {
  heatmap: HeatmapResponse | undefined;
  isLoadingHeatmap: boolean;
  selectedRoute: AnalyzedRoute | undefined;
}

const LAYER_OPTIONS: {
  id: HeatmapLayerMode;
  label: string;
  icon: React.ReactNode;
}[] = [
  { id: "risk", label: "Overall Risk", icon: <Flame className="w-3.5 h-3.5" /> },
  { id: "wind", label: "Wind (mph)", icon: <Wind className="w-3.5 h-3.5" /> },
  {
    id: "rain",
    label: "Rain (in/hr)",
    icon: <CloudRain className="w-3.5 h-3.5" />,
  },
  {
    id: "snow",
    label: "Snow (in/hr)",
    icon: <Snowflake className="w-3.5 h-3.5" />,
  },
];

export const HeatmapTimelineBar: React.FC<HeatmapTimelineBarProps> = ({
  heatmap,
  isLoadingHeatmap,
  selectedRoute,
}) => {
  const {
    heatmapEnabled,
    heatmapLayer,
    heatmapOpacity,
    sliderHour,
    isPlaying,
    playbackSpeedMs,
    setHeatmapEnabled,
    setHeatmapLayer,
    setHeatmapOpacity,
    setSliderHour,
    setIsPlaying,
    setPlaybackSpeedMs,
  } = useTripStore();

  // Playback loop (HM-4)
  useEffect(() => {
    if (!isPlaying) return;
    const timer = window.setInterval(() => {
      setSliderHour((prev) => (prev >= 48 ? 0 : prev + 1));
    }, playbackSpeedMs);
    return () => window.clearInterval(timer);
  }, [isPlaying, playbackSpeedMs, setSliderHour]);

  const currentHourLabel =
    heatmap?.hourLabels?.[sliderHour] ?? `+${sliderHour}h from departure`;

  const truckPos =
    selectedRoute && heatmap?.truckPositions?.[selectedRoute.id]?.[sliderHour];

  const tripDurationHours = selectedRoute
    ? Math.min(48, Math.ceil(selectedRoute.durationMin / 60))
    : 0;

  return (
    <div className="bg-slate-900/95 backdrop-blur-md border border-slate-700/80 rounded-xl p-3 shadow-2xl space-y-2">
      {/* Row 1: Play/Pause + 0-48h Scrubber + Speed + Opacity */}
      <div className="flex flex-wrap items-center gap-2.5">
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => setIsPlaying(!isPlaying)}
            aria-label={isPlaying ? "Pause timeline" : "Play timeline"}
            className="p-2 rounded-lg bg-sky-500 hover:bg-sky-400 text-slate-950 font-bold transition shadow"
          >
            {isPlaying ? (
              <Pause className="w-4 h-4" />
            ) : (
              <Play className="w-4 h-4" />
            )}
          </button>
          <button
            type="button"
            onClick={() => {
              setIsPlaying(false);
              setSliderHour((h) => Math.max(0, h - 1));
            }}
            aria-label="Previous Hour"
            className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
          <button
            type="button"
            onClick={() => {
              setIsPlaying(false);
              setSliderHour((h) => Math.min(48, h + 1));
            }}
            aria-label="Next Hour"
            className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>

        {/* 0-48h Slider with Active Trip Window Highlight (HM-4, HM-8) */}
        <div className="flex-1 min-w-[200px] relative">
          <div className="flex items-center justify-between text-xs mb-0.5">
            <span className="font-mono font-bold text-sky-300">
              Hour +{sliderHour}h{" "}
              <span className="text-slate-300 font-normal">
                ({currentHourLabel})
              </span>
            </span>
            <div className="flex items-center gap-2">
              {isLoadingHeatmap ? (
                <span className="text-sky-400 animate-pulse font-mono text-[11px]">
                  Loading 49h grid...
                </span>
              ) : (
                <span className="text-[11px] text-slate-400 hidden sm:inline">
                  Trip window: 0h – +{tripDurationHours}h
                </span>
              )}
              <select
                value={playbackSpeedMs}
                onChange={(e) => setPlaybackSpeedMs(Number(e.target.value))}
                aria-label="Playback Speed"
                className="bg-slate-800 border border-slate-700 rounded px-1.5 py-0.5 text-[11px] text-slate-200"
              >
                <option value={700}>1x</option>
                <option value={350}>2x</option>
                <option value={150}>4x</option>
              </select>
            </div>
          </div>

          <div className="relative flex items-center">
            {tripDurationHours > 0 && (
              <div
                style={{
                  width: `${Math.min(100, (tripDurationHours / 48) * 100)}%`,
                }}
                className="absolute left-0 h-1.5 bg-sky-500/35 rounded-l pointer-events-none"
                title={`Truck active transit window: 0h to +${tripDurationHours}h`}
              />
            )}
            <input
              type="range"
              min={0}
              max={48}
              step={1}
              value={sliderHour}
              onChange={(e) => {
                setIsPlaying(false);
                setSliderHour(Number(e.target.value));
              }}
              aria-label="Corridor Forecast Timeline Slider (0 to 48 hours)"
              aria-valuemin={0}
              aria-valuemax={48}
              aria-valuenow={sliderHour}
              className="w-full accent-sky-400 cursor-pointer z-10"
            />
          </div>

          <div className="flex justify-between text-[10px] font-mono text-slate-500">
            <span>0h (Depart)</span>
            <span>+12h</span>
            <span>+24h</span>
            <span>+36h</span>
            <span>+48h</span>
          </div>
        </div>
      </div>

      {/* Row 2: Compact Truck Live Status + Layer Switcher & Opacity */}
      <div className="flex flex-wrap items-center justify-between gap-2 pt-1.5 border-t border-slate-800/80 text-xs">
        {/* Truck Position Status at Slider Hour (HM-8) */}
        {truckPos ? (
          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-sky-500/15 text-sky-300 border border-sky-500/30 font-semibold">
              <Truck className="w-3.5 h-3.5" />
              {truckPos.arrived
                ? "Arrived at Destination"
                : `Truck @ Mile ${truckPos.mile.toFixed(0)}`}
            </span>
            <span className="text-slate-300 font-medium">{truckPos.place}</span>
            {truckPos.windMph !== null && (
              <span className="font-mono text-[11px] text-slate-400 hidden md:inline">
                ({truckPos.windMph.toFixed(0)} mph · R:{" "}
                {(truckPos.rainInHr ?? 0).toFixed(2)}&quot; · S:{" "}
                {(truckPos.snowInHr ?? 0).toFixed(2)}&quot;)
              </span>
            )}
            <span
              className={`px-2 py-0.5 rounded border text-[11px] ${
                RISK_BADGE_CLASSES[truckPos.level]
              }`}
            >
              {RISK_SHAPES[truckPos.level]} {truckPos.level}
            </span>
          </div>
        ) : (
          <div className="text-[11px] text-slate-400">
            Scrub 0h–48h to inspect hourly corridor weather
          </div>
        )}

        {/* Layer Switcher + Opacity */}
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => setHeatmapEnabled(!heatmapEnabled)}
            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold border transition ${
              heatmapEnabled
                ? "bg-sky-500/20 text-sky-300 border-sky-500/50"
                : "bg-slate-800 text-slate-400 border-slate-700"
            }`}
          >
            {heatmapEnabled ? (
              <Eye className="w-3 h-3" />
            ) : (
              <EyeOff className="w-3 h-3" />
            )}
            <span className="hidden sm:inline">Heatmap</span>
          </button>

          <div
            role="group"
            aria-label="Heatmap Layer Mode"
            className="inline-flex rounded-lg bg-slate-950/80 p-0.5 border border-slate-800"
          >
            {LAYER_OPTIONS.map((opt) => (
              <button
                key={opt.id}
                type="button"
                onClick={() => {
                  setHeatmapEnabled(true);
                  setHeatmapLayer(opt.id);
                }}
                className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium transition ${
                  heatmapLayer === opt.id && heatmapEnabled
                    ? "bg-sky-500 text-slate-950 font-semibold shadow"
                    : "text-slate-300 hover:text-white"
                }`}
              >
                {opt.icon}
                <span>{opt.label}</span>
              </button>
            ))}
          </div>

          <label className="flex items-center gap-1 text-[11px] text-slate-400">
            <span>Opacity</span>
            <input
              type="range"
              min={0.2}
              max={1}
              step={0.05}
              value={heatmapOpacity}
              onChange={(e) => setHeatmapOpacity(Number(e.target.value))}
              aria-label="Heatmap Opacity"
              className="w-14 accent-sky-400 cursor-pointer"
            />
          </label>
        </div>
      </div>
    </div>
  );
};
