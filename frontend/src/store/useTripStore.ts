import { create } from "zustand";
import type {
  GeocodeLocation,
  HeatmapLayerMode,
  RouteCheckpoint,
} from "../types/api";
import { getNextQuarterHourLocalIso, SAMPLE_TRIPS } from "../utils/risk";

interface TripStoreState {
  // Form Inputs
  origin: GeocodeLocation;
  destination: GeocodeLocation;
  departureTimeLocal: string;
  loadWeightLb: number;
  weightUnit: "lb" | "kg";
  intervalMiles: 10 | 25 | 50;
  gustAware: boolean;
  demoStormMode: boolean;

  // Interactive Map & Selection State
  selectedRouteId: string | null;
  hoveredRouteId: string | null;
  selectedCheckpoint: RouteCheckpoint | null;

  // Heatmap Controls (0-48h slider)
  heatmapEnabled: boolean;
  heatmapLayer: HeatmapLayerMode;
  heatmapOpacity: number;
  sliderHour: number;
  isPlaying: boolean;
  playbackSpeedMs: number;

  // Active Bottom/Detail Tab
  activeDetailTab: "checkpoints" | "departure-window" | "rules";

  // Actions
  setOrigin: (loc: GeocodeLocation) => void;
  setDestination: (loc: GeocodeLocation) => void;
  swapLocations: () => void;
  setDepartureTimeLocal: (val: string) => void;
  setLoadWeightLb: (lb: number) => void;
  setWeightUnit: (unit: "lb" | "kg") => void;
  setIntervalMiles: (interval: 10 | 25 | 50) => void;
  setGustAware: (val: boolean) => void;
  setDemoStormMode: (val: boolean) => void;
  applySampleTrip: (sampleId: string, enableStorm?: boolean) => void;

  setSelectedRouteId: (id: string | null) => void;
  setHoveredRouteId: (id: string | null) => void;
  setSelectedCheckpoint: (cp: RouteCheckpoint | null) => void;

  setHeatmapEnabled: (val: boolean) => void;
  setHeatmapLayer: (mode: HeatmapLayerMode) => void;
  setHeatmapOpacity: (opacity: number) => void;
  setSliderHour: (hour: number | ((prev: number) => number)) => void;
  setIsPlaying: (playing: boolean) => void;
  setPlaybackSpeedMs: (ms: number) => void;
  setActiveDetailTab: (tab: "checkpoints" | "departure-window" | "rules") => void;
}

function getInitialUrlState() {
  if (typeof window === "undefined") {
    return {
      demoStorm: true,
      loadWeightLb: 35000,
      intervalMiles: 25 as const,
    };
  }
  const params = new URLSearchParams(window.location.search);
  const demoParam = params.get("demo");
  // Default demo storm mode on when ?demo=storm or by default so reviewers see Severe/No Travel rules immediately
  const demoStorm =
    demoParam === null ? true : demoParam === "storm" || demoParam === "1";
  const weightParam = Number(params.get("weight"));
  const loadWeightLb =
    Number.isFinite(weightParam) && weightParam > 0 ? weightParam : 35000;
  const intervalParam = Number(params.get("interval"));
  const intervalMiles: 10 | 25 | 50 =
    intervalParam === 10 || intervalParam === 25 || intervalParam === 50
      ? intervalParam
      : 25;

  return { demoStorm, loadWeightLb, intervalMiles };
}

const initialUrl = getInitialUrlState();

export const useTripStore = create<TripStoreState>((set) => ({
  origin: SAMPLE_TRIPS[0].origin,
  destination: SAMPLE_TRIPS[0].destination,
  departureTimeLocal: getNextQuarterHourLocalIso(),
  loadWeightLb: initialUrl.loadWeightLb,
  weightUnit: "lb",
  intervalMiles: initialUrl.intervalMiles,
  gustAware: false,
  demoStormMode: initialUrl.demoStorm,

  selectedRouteId: null,
  hoveredRouteId: null,
  selectedCheckpoint: null,

  heatmapEnabled: true,
  heatmapLayer: "risk",
  heatmapOpacity: 0.72,
  sliderHour: 6,
  isPlaying: false,
  playbackSpeedMs: 450,

  activeDetailTab: "checkpoints",

  setOrigin: (origin) => set({ origin }),
  setDestination: (destination) => set({ destination }),
  swapLocations: () =>
    set((state) => ({
      origin: state.destination,
      destination: state.origin,
      selectedCheckpoint: null,
    })),
  setDepartureTimeLocal: (departureTimeLocal) => set({ departureTimeLocal }),
  setLoadWeightLb: (loadWeightLb) => set({ loadWeightLb }),
  setWeightUnit: (weightUnit) => set({ weightUnit }),
  setIntervalMiles: (intervalMiles) => set({ intervalMiles }),
  setGustAware: (gustAware) => set({ gustAware }),
  setDemoStormMode: (demoStormMode) => set({ demoStormMode }),

  applySampleTrip: (sampleId, enableStorm) => {
    const trip =
      SAMPLE_TRIPS.find((t) => t.id === sampleId) ?? SAMPLE_TRIPS[0];
    set((state) => ({
      origin: trip.origin,
      destination: trip.destination,
      loadWeightLb: trip.loadWeightLb,
      intervalMiles: trip.intervalMiles,
      demoStormMode:
        enableStorm !== undefined ? enableStorm : state.demoStormMode,
      selectedCheckpoint: null,
    }));
  },

  setSelectedRouteId: (selectedRouteId) =>
    set({ selectedRouteId, selectedCheckpoint: null }),
  setHoveredRouteId: (hoveredRouteId) => set({ hoveredRouteId }),
  setSelectedCheckpoint: (selectedCheckpoint) => set({ selectedCheckpoint }),

  setHeatmapEnabled: (heatmapEnabled) => set({ heatmapEnabled }),
  setHeatmapLayer: (heatmapLayer) => set({ heatmapLayer }),
  setHeatmapOpacity: (heatmapOpacity) => set({ heatmapOpacity }),
  setSliderHour: (hourOrFn) =>
    set((state) => ({
      sliderHour:
        typeof hourOrFn === "function" ? hourOrFn(state.sliderHour) : hourOrFn,
    })),
  setIsPlaying: (isPlaying) => set({ isPlaying }),
  setPlaybackSpeedMs: (playbackSpeedMs) => set({ playbackSpeedMs }),
  setActiveDetailTab: (activeDetailTab) => set({ activeDetailTab }),
}));
