import { describe, it, expect, beforeEach } from "vitest";
import {
  RISK_COLORS,
  RISK_SHAPES,
  formatDuration,
  SAMPLE_TRIPS,
  LOAD_PRESETS_LB,
} from "../utils/risk";
import { useTripStore } from "../store/useTripStore";

describe("Risk Metadata & Formatting Utilities", () => {
  it("defines distinct color and shape symbols for all 6 risk levels (MP-3, MP-8)", () => {
    const levels = [
      "Low",
      "Moderate",
      "High",
      "Severe",
      "No Travel",
      "Unknown",
    ] as const;
    const colors = new Set(levels.map((l) => RISK_COLORS[l]));
    const shapes = new Set(levels.map((l) => RISK_SHAPES[l]));
    expect(colors.size).toBe(6);
    expect(shapes.size).toBe(6);
  });

  it("formats trip durations accurately", () => {
    expect(formatDuration(0)).toBe("0m");
    expect(formatDuration(45)).toBe("45m");
    expect(formatDuration(120)).toBe("2h");
    expect(formatDuration(870)).toBe("14h 30m");
  });

  it("includes curated sample trips and load weight presets", () => {
    expect(SAMPLE_TRIPS.length).toBeGreaterThanOrEqual(2);
    expect(LOAD_PRESETS_LB).toEqual([20000, 35000, 45000, 80000]);
  });
});

describe("Trip Store State Management", () => {
  beforeEach(() => {
    useTripStore.setState({
      origin: SAMPLE_TRIPS[0].origin,
      destination: SAMPLE_TRIPS[0].destination,
      loadWeightLb: 45000,
      sliderHour: 0,
      heatmapLayer: "risk",
      weightUnit: "lb",
    });
  });

  it("updates load weight, slider hour, and swaps origin/destination", () => {
    const store = useTripStore.getState();
    const initialOrigin = store.origin;
    const initialDest = store.destination;

    store.setLoadWeightLb(20000);
    expect(useTripStore.getState().loadWeightLb).toBe(20000);

    store.setSliderHour(24);
    expect(useTripStore.getState().sliderHour).toBe(24);

    store.swapLocations();
    expect(useTripStore.getState().origin.label).toBe(initialDest.label);
    expect(useTripStore.getState().destination.label).toBe(initialOrigin.label);
  });
});
