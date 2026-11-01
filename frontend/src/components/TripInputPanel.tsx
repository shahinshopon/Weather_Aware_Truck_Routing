import React from "react";
import {
  ArrowUpDown,
  CalendarClock,
  CloudLightning,
  Gauge,
  Navigation,
  Scale,
  Sparkles,
  AlertTriangle,
  Wind,
} from "lucide-react";
import { useTripStore } from "../store/useTripStore";
import { LOAD_PRESETS_LB, SAMPLE_TRIPS } from "../utils/risk";
import { LocationAutocomplete } from "./LocationAutocomplete";

interface TripInputPanelProps {
  onSubmit: () => void;
  isLoading: boolean;
  loadingStage: string;
}

const LB_PER_KG = 2.20462262;

export const TripInputPanel: React.FC<TripInputPanelProps> = ({
  onSubmit,
  isLoading,
  loadingStage,
}) => {
  const {
    origin,
    destination,
    departureTimeLocal,
    loadWeightLb,
    weightUnit,
    intervalMiles,
    gustAware,
    demoStormMode,
    setOrigin,
    setDestination,
    swapLocations,
    setDepartureTimeLocal,
    setLoadWeightLb,
    setWeightUnit,
    setIntervalMiles,
    setGustAware,
    setDemoStormMode,
    applySampleTrip,
  } = useTripStore();

  const displayedWeight =
    weightUnit === "lb"
      ? Math.round(loadWeightLb)
      : Math.round(loadWeightLb / LB_PER_KG);

  const handleWeightChange = (valStr: string) => {
    const raw = Number(valStr);
    if (!Number.isFinite(raw)) {
      setLoadWeightLb(0);
      return;
    }
    const lb = weightUnit === "lb" ? raw : raw * LB_PER_KG;
    setLoadWeightLb(Math.max(0, Math.round(lb)));
  };

  const isSameOriginDest =
    origin.label.trim().toLowerCase() ===
      destination.label.trim().toLowerCase() && origin.label.trim() !== "";

  const isWeightInvalid = !Number.isFinite(loadWeightLb) || loadWeightLb <= 0;
  const isOverGrossSoftLimit = loadWeightLb > 80000;

  const isFormValid =
    origin.label.trim().length >= 2 &&
    destination.label.trim().length >= 2 &&
    !isSameOriginDest &&
    !isWeightInvalid &&
    Boolean(departureTimeLocal);

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (isFormValid && !isLoading) {
          onSubmit();
        }
      }}
      className="bg-slate-900/95 border border-slate-800 rounded-xl p-4 shadow-xl space-y-3.5"
    >
      {/* Sample Trips & Demo Mode Header Bar */}
      <div className="flex flex-wrap items-center justify-between gap-2 pb-2 border-b border-slate-800/80">
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1">
            <Sparkles className="w-3.5 h-3.5 text-sky-400" />
            Sample Trips:
          </span>
          {SAMPLE_TRIPS.map((sample) => (
            <button
              key={sample.id}
              type="button"
              onClick={() => {
                applySampleTrip(sample.id);
                setTimeout(() => onSubmit(), 20);
              }}
              className="text-xs px-2.5 py-1 rounded-md bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700/80 transition"
            >
              {sample.name}
            </button>
          ))}
        </div>

        {/* Synthetic Severe Weather Demo Toggle (UX-6) */}
        <button
          type="button"
          onClick={() => {
            setDemoStormMode(!demoStormMode);
            setTimeout(() => onSubmit(), 20);
          }}
          title="Injects deterministic High Plains & Red River severe storm conditions so 30,000 lb and 40,000 lb load rules can be tested anytime"
          className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium border transition ${
            demoStormMode
              ? "bg-amber-500/20 text-amber-200 border-amber-500/60 shadow-sm"
              : "bg-slate-800/80 text-slate-400 border-slate-700 hover:text-slate-200"
          }`}
        >
          <CloudLightning
            className={`w-3.5 h-3.5 ${
              demoStormMode ? "text-amber-400" : "text-slate-400"
            }`}
          />
          <span>Storm Demo: {demoStormMode ? "ON" : "OFF"}</span>
        </button>
      </div>

      {/* Origin + Swap + Destination */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-end gap-2">
        <LocationAutocomplete
          label="Origin"
          value={origin}
          onChange={setOrigin}
          accentColorClass="text-emerald-400"
        />
        <button
          type="button"
          onClick={swapLocations}
          title="Swap Origin and Destination"
          aria-label="Swap Origin and Destination"
          className="self-center sm:self-end p-2 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300 transition"
        >
          <ArrowUpDown className="w-4 h-4 sm:rotate-90" />
        </button>
        <LocationAutocomplete
          label="Destination"
          value={destination}
          onChange={setDestination}
          accentColorClass="text-rose-400"
        />
      </div>

      {isSameOriginDest && (
        <p className="text-xs text-red-400 flex items-center gap-1.5">
          <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
          Origin and destination must be different locations.
        </p>
      )}

      {/* Departure Time & Checkpoint Interval */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div>
          <label
            htmlFor="departure-time-input"
            className="block text-[11px] font-semibold uppercase tracking-wider text-slate-400 mb-1"
          >
            Departure Date & Time (Origin Local)
          </label>
          <div className="relative">
            <CalendarClock className="w-4 h-4 text-sky-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
            <input
              id="departure-time-input"
              type="datetime-local"
              value={departureTimeLocal}
              onChange={(e) => setDepartureTimeLocal(e.target.value)}
              className="w-full bg-slate-900 border border-slate-700/80 rounded-lg pl-9 pr-3 py-1.5 text-sm text-slate-100 focus:outline-none focus:ring-2 focus:ring-sky-500/60"
            />
          </div>
        </div>

        <div>
          <span className="block text-[11px] font-semibold uppercase tracking-wider text-slate-400 mb-1">
            Checkpoint Sampling Interval
          </span>
          <div
            role="group"
            aria-label="Checkpoint Interval Miles"
            className="grid grid-cols-3 gap-1.5 bg-slate-950/70 p-1 rounded-lg border border-slate-800"
          >
            {([10, 25, 50] as const).map((miles) => (
              <button
                key={miles}
                type="button"
                onClick={() => {
                  setIntervalMiles(miles);
                  setTimeout(() => onSubmit(), 20);
                }}
                className={`py-1 rounded-md text-xs font-semibold transition flex items-center justify-center gap-1 ${
                  intervalMiles === miles
                    ? "bg-sky-500 text-slate-950 shadow"
                    : "text-slate-300 hover:bg-slate-800"
                }`}
              >
                <Gauge className="w-3 h-3" />
                {miles} mi
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Cargo Load Weight + Presets (IN-3) */}
      <div className="space-y-1.5">
        <div className="flex items-center justify-between">
          <label
            htmlFor="load-weight-input"
            className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1"
          >
            <Scale className="w-3.5 h-3.5 text-sky-400" />
            Cargo Load Weight ({weightUnit})
          </label>
          <div className="flex items-center gap-1 text-[11px]">
            <button
              type="button"
              onClick={() => setWeightUnit("lb")}
              className={`px-2 py-0.5 rounded ${
                weightUnit === "lb"
                  ? "bg-sky-500/20 text-sky-300 border border-sky-500/40 font-semibold"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              lb
            </button>
            <button
              type="button"
              onClick={() => setWeightUnit("kg")}
              className={`px-2 py-0.5 rounded ${
                weightUnit === "kg"
                  ? "bg-sky-500/20 text-sky-300 border border-sky-500/40 font-semibold"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              kg
            </button>
          </div>
        </div>

        <div className="flex flex-col sm:flex-row gap-2">
          <input
            id="load-weight-input"
            type="number"
            min={1}
            step={500}
            value={displayedWeight || ""}
            onChange={(e) => handleWeightChange(e.target.value)}
            className="sm:w-36 bg-slate-900 border border-slate-700/80 rounded-lg px-3 py-1.5 text-sm font-mono text-slate-100 focus:outline-none focus:ring-2 focus:ring-sky-500/60"
          />

          {/* Quick Weight Presets: 20,000 / 35,000 / 45,000 / 80,000 lb */}
          <div className="flex-1 grid grid-cols-4 gap-1.5">
            {LOAD_PRESETS_LB.map((presetLb) => {
              const active = Math.abs(loadWeightLb - presetLb) < 50;
              return (
                <button
                  key={presetLb}
                  type="button"
                  onClick={() => {
                    setLoadWeightLb(presetLb);
                    setTimeout(() => onSubmit(), 20);
                  }}
                  title={
                    presetLb === 20000
                      ? "20,000 lb: Below both wind escalation thresholds"
                      : presetLb === 35000
                      ? "35,000 lb: Triggers >30,000 lb No Travel rule at 45–54.9 mph wind"
                      : presetLb === 45000
                      ? "45,000 lb: Triggers both >30k lb (No Travel) and >40k lb (Severe at 35–44.9 mph) wind rules"
                      : "80,000 lb: Typical US gross limit"
                  }
                  className={`py-1.5 px-2 rounded-lg text-xs font-mono font-medium border transition ${
                    active
                      ? "bg-sky-500/25 border-sky-400 text-sky-200 shadow-sm"
                      : "bg-slate-800/80 border-slate-700/80 text-slate-300 hover:bg-slate-800"
                  }`}
                >
                  {(presetLb / 1000).toFixed(0)}k lb
                </button>
              );
            })}
          </div>
        </div>

        {/* Active Load Rule Indicator Pills */}
        <div className="flex flex-wrap items-center justify-between gap-2 pt-0.5 text-[11px]">
          <div className="flex flex-wrap items-center gap-1.5">
            <span
              className={`px-2 py-0.5 rounded border ${
                loadWeightLb > 30000
                  ? "bg-red-500/15 border-red-500/40 text-red-300 font-medium"
                  : "bg-slate-800/50 border-slate-800 text-slate-500"
              }`}
            >
              {loadWeightLb > 30000 ? "✓" : "○"} &gt;30k lb Rule (45–55 mph → No
              Travel)
            </span>
            <span
              className={`px-2 py-0.5 rounded border ${
                loadWeightLb > 40000
                  ? "bg-orange-500/15 border-orange-500/40 text-orange-300 font-medium"
                  : "bg-slate-800/50 border-slate-800 text-slate-500"
              }`}
            >
              {loadWeightLb > 40000 ? "✓" : "○"} &gt;40k lb Rule (35–45 mph →
              Severe)
            </span>
          </div>

          <label className="inline-flex items-center gap-1.5 text-slate-400 hover:text-slate-200 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={gustAware}
              onChange={(e) => {
                setGustAware(e.target.checked);
                setTimeout(() => onSubmit(), 20);
              }}
              className="rounded border-slate-700 bg-slate-900 text-sky-500 focus:ring-sky-500/40"
            />
            <Wind className="w-3 h-3 text-sky-400" />
            <span>Gust-aware wind</span>
          </label>
        </div>

        {isWeightInvalid && (
          <p className="text-xs text-red-400">
            Cargo load weight must be greater than 0 lb.
          </p>
        )}

        {isOverGrossSoftLimit && (
          <div className="flex items-center gap-1.5 text-xs text-amber-300 bg-amber-500/10 border border-amber-500/30 rounded-md px-2.5 py-1.5">
            <AlertTriangle className="w-3.5 h-3.5 shrink-0 text-amber-400" />
            <span>
              Soft warning: {Math.round(loadWeightLb).toLocaleString()} lb
              exceeds 80,000 lb (typical US gross vehicle limit). Analysis
              proceeds without blocking.
            </span>
          </div>
        )}
      </div>

      {/* Submit Button */}
      <button
        type="submit"
        disabled={!isFormValid || isLoading}
        className="w-full py-2.5 px-4 rounded-lg bg-gradient-to-r from-sky-500 to-blue-600 hover:from-sky-400 hover:to-blue-500 disabled:opacity-50 disabled:cursor-not-allowed text-slate-950 font-bold text-sm shadow-lg shadow-sky-500/15 flex items-center justify-center gap-2 transition"
      >
        <Navigation className="w-4 h-4" />
        <span>
          {isLoading
            ? loadingStage || "Analyzing Routes & ETA Weather..."
            : "Analyze 3 Truck Routes & Weather Risk"}
        </span>
      </button>
    </form>
  );
};
