import React, { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import type {
  AnalysisResponse,
  AnalyzedRoute,
  HeatmapResponse,
  RiskLevelLabel,
  RouteCheckpoint,
} from "../types/api";
import { RISK_COLORS, RISK_SHAPES } from "../utils/risk";
import { useTripStore } from "../store/useTripStore";
import {
  Layers,
  ShieldAlert,
  Wind,
  CloudRain,
  Snowflake,
  Navigation,
  Eye,
  EyeOff,
  Flame,
  ChevronUp,
  ChevronDown,
} from "lucide-react";

interface CorridorMapProps {
  analysis: AnalysisResponse | undefined;
  heatmap: HeatmapResponse | undefined;
}

const OFFLINE_SAFE_STYLE: maplibregl.StyleSpecification = {
  version: 8,
  name: "Freight Dark Dispatch",
  sources: {
    "esri-dark-base": {
      type: "raster",
      tiles: [
        "https://services.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}",
      ],
      tileSize: 256,
      attribution: "&copy; Esri, HERE, Garmin, OpenStreetMap contributors",
    },
    "esri-dark-labels": {
      type: "raster",
      tiles: [
        "https://services.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}",
      ],
      tileSize: 256,
    },
  },
  layers: [
    {
      id: "background-fill",
      type: "background",
      paint: {
        "background-color": "#0b1120",
      },
    },
    {
      id: "esri-dark-base-layer",
      type: "raster",
      source: "esri-dark-base",
      minzoom: 0,
      maxzoom: 16,
      paint: {
        "raster-opacity": 0.95,
      },
    },
    {
      id: "esri-dark-labels-layer",
      type: "raster",
      source: "esri-dark-labels",
      minzoom: 0,
      maxzoom: 16,
      paint: {
        "raster-opacity": 0.9,
      },
    },
  ],
};

function buildUSGraticuleGeoJSON(): GeoJSON.FeatureCollection {
  const features: GeoJSON.Feature[] = [];
  for (let lon = -125; lon <= -65; lon += 5) {
    features.push({
      type: "Feature",
      properties: { label: `${Math.abs(lon)}°W` },
      geometry: {
        type: "LineString",
        coordinates: [
          [lon, 24],
          [lon, 50],
        ],
      },
    });
  }
  for (let lat = 25; lat <= 50; lat += 5) {
    features.push({
      type: "Feature",
      properties: { label: `${lat}°N` },
      geometry: {
        type: "LineString",
        coordinates: [
          [-125, lat],
          [-65, lat],
        ],
      },
    });
  }
  return { type: "FeatureCollection", features };
}

function buildHeatmapGeoJSON(
  heatmap: HeatmapResponse | undefined,
  hourIndex: number
): GeoJSON.FeatureCollection {
  if (!heatmap || !heatmap.cells) {
    return { type: "FeatureCollection", features: [] };
  }
  const idx = Math.max(0, Math.min(48, Math.round(hourIndex)));
  const features: GeoJSON.Feature[] = heatmap.cells.map((cell) => {
    const riskScore = cell.risk[idx] ?? 0;
    const windVal = cell.wind[idx] ?? 0;
    const rainVal = cell.rain[idx] ?? 0;
    const snowVal = cell.snow[idx] ?? 0;
    return {
      type: "Feature",
      properties: {
        risk: riskScore,
        wind: windVal,
        rain: rainVal,
        snow: snowVal,
      },
      geometry: {
        type: "Point",
        coordinates: [cell.lng, cell.lat],
      },
    };
  });
  return { type: "FeatureCollection", features };
}

function buildNonSelectedRoutesGeoJSON(
  routes: AnalyzedRoute[],
  selectedRouteId: string | null
): GeoJSON.FeatureCollection {
  const palette = ["#64748b", "#475569", "#94a3b8"];
  const features: GeoJSON.Feature[] = routes
    .filter((r) => r.id !== selectedRouteId)
    .map((route, i) => ({
      type: "Feature",
      properties: {
        routeId: route.id,
        name: route.label,
        color: palette[i % palette.length],
      },
      geometry: {
        type: "LineString",
        coordinates: route.coordinates.map(([lat, lng]) => [lng, lat]),
      },
    }));
  return { type: "FeatureCollection", features };
}

function buildSelectedRouteSegmentsGeoJSON(
  selectedRoute: AnalyzedRoute | undefined
): GeoJSON.FeatureCollection {
  if (!selectedRoute) {
    return { type: "FeatureCollection", features: [] };
  }
  const features: GeoJSON.Feature[] = selectedRoute.riskSegments.map(
    (seg, i) => ({
      type: "Feature",
      properties: {
        segmentIndex: i,
        overallRisk: seg.level,
        color: RISK_COLORS[seg.level] ?? "#64748b",
      },
      geometry: {
        type: "LineString",
        coordinates: seg.coordinates,
      },
    })
  );
  return { type: "FeatureCollection", features };
}

const ORDERED_LEVELS: RiskLevelLabel[] = [
  "Low",
  "Moderate",
  "High",
  "Severe",
  "No Travel",
  "Unknown",
];

export const CorridorMap: React.FC<CorridorMapProps> = ({
  analysis,
  heatmap,
}) => {
  const {
    selectedRouteId,
    setSelectedRouteId,
    selectedCheckpoint,
    setSelectedCheckpoint,
    heatmapEnabled,
    heatmapLayer,
    heatmapOpacity,
    sliderHour,
    setHeatmapEnabled,
    setHeatmapLayer,
  } = useTripStore();

  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [mapLoaded, setMapLoaded] = useState(false);
  const [showLegendDetails, setShowLegendDetails] = useState(false);
  const markersRef = useRef<maplibregl.Marker[]>([]);
  const truckMarkerRef = useRef<maplibregl.Marker | null>(null);
  const originDestMarkersRef = useRef<maplibregl.Marker[]>([]);
  const activePopupRef = useRef<maplibregl.Popup | null>(null);

  const selectedRoute =
    analysis?.routes.find((r) => r.id === selectedRouteId) ??
    analysis?.routes[0];

  // Initialize MapLibre GL map once
  useEffect(() => {
    if (!mapContainerRef.current || mapRef.current) return;

    const map = new maplibregl.Map({
      container: mapContainerRef.current,
      style: OFFLINE_SAFE_STYLE,
      center: [-96.5, 39.8],
      zoom: 4.5,
      attributionControl: false,
    });

    map.addControl(
      new maplibregl.NavigationControl({ showCompass: true }),
      "top-right"
    );

    map.on("load", () => {
      map.addSource("graticule", {
        type: "geojson",
        data: buildUSGraticuleGeoJSON(),
      });
      map.addLayer({
        id: "graticule-lines",
        type: "line",
        source: "graticule",
        paint: {
          "line-color": "#1e293b",
          "line-width": 1,
          "line-dasharray": [2, 4],
          "line-opacity": 0.5,
        },
      });

      // Corridor Heatmap Source & GPU Layers (HM-5, HM-6, HM-7)
      map.addSource("corridor-heatmap", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });

      map.addLayer({
        id: "corridor-heatmap-glow",
        type: "circle",
        source: "corridor-heatmap",
        paint: {
          "circle-radius": [
            "interpolate",
            ["linear"],
            ["zoom"],
            3,
            14,
            5,
            24,
            7,
            40,
            9,
            64,
          ],
          "circle-blur": 0.85,
          "circle-opacity": 0.4,
          "circle-color": [
            "interpolate",
            ["linear"],
            ["get", "risk"],
            0,
            "#10b981",
            1,
            "#eab308",
            2,
            "#f97316",
            3,
            "#ef4444",
            4,
            "#991b1b",
          ],
        },
      });

      map.addLayer({
        id: "corridor-heatmap-dots",
        type: "circle",
        source: "corridor-heatmap",
        paint: {
          "circle-radius": [
            "interpolate",
            ["linear"],
            ["zoom"],
            3,
            2.5,
            6,
            4.5,
            9,
            7,
          ],
          "circle-opacity": 0.5,
          "circle-color": [
            "interpolate",
            ["linear"],
            ["get", "risk"],
            0,
            "#10b981",
            1,
            "#eab308",
            2,
            "#f97316",
            3,
            "#ef4444",
            4,
            "#991b1b",
          ],
        },
      });

      // Non-selected routes source & layer (MP-1)
      map.addSource("non-selected-routes", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });

      map.addLayer({
        id: "non-selected-routes-hit",
        type: "line",
        source: "non-selected-routes",
        layout: {
          "line-join": "round",
          "line-cap": "round",
        },
        paint: {
          "line-color": "#94a3b8",
          "line-width": 14,
          "line-opacity": 0.08,
        },
      });

      map.addLayer({
        id: "non-selected-routes-line",
        type: "line",
        source: "non-selected-routes",
        layout: {
          "line-join": "round",
          "line-cap": "round",
        },
        paint: {
          "line-color": ["get", "color"],
          "line-width": 4,
          "line-opacity": 0.72,
          "line-dasharray": [2, 1.5],
        },
      });

      // Selected route casing + risk-colored segments (MP-2)
      map.addSource("selected-route-segments", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });

      map.addLayer({
        id: "selected-route-casing",
        type: "line",
        source: "selected-route-segments",
        layout: {
          "line-join": "round",
          "line-cap": "round",
        },
        paint: {
          "line-color": "#020617",
          "line-width": 10,
          "line-opacity": 0.9,
        },
      });

      map.addLayer({
        id: "selected-route-line",
        type: "line",
        source: "selected-route-segments",
        layout: {
          "line-join": "round",
          "line-cap": "round",
        },
        paint: {
          "line-color": ["get", "color"],
          "line-width": 6,
          "line-opacity": 0.96,
        },
      });

      // Click handler on non-selected routes to select them
      map.on("click", "non-selected-routes-hit", (e) => {
        const feature = e.features?.[0];
        const routeId = feature?.properties?.routeId;
        if (routeId) {
          setSelectedRouteId(routeId);
        }
      });

      map.on("mouseenter", "non-selected-routes-hit", () => {
        map.getCanvas().style.cursor = "pointer";
      });
      map.on("mouseleave", "non-selected-routes-hit", () => {
        map.getCanvas().style.cursor = "";
      });

      setMapLoaded(true);
    });

    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, [setSelectedRouteId]);

  // Update GPU Heatmap layer data & color expression when heatmap, sliderHour, heatmapLayer, or visibility changes (HM-6, HM-7)
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded) return;

    const source = map.getSource("corridor-heatmap") as
      | maplibregl.GeoJSONSource
      | undefined;
    if (!source) return;

    const visibility = heatmapEnabled ? "visible" : "none";
    if (map.getLayer("corridor-heatmap-glow")) {
      map.setLayoutProperty("corridor-heatmap-glow", "visibility", visibility);
      map.setPaintProperty(
        "corridor-heatmap-glow",
        "circle-opacity",
        heatmapOpacity * 0.55
      );
    }
    if (map.getLayer("corridor-heatmap-dots")) {
      map.setLayoutProperty("corridor-heatmap-dots", "visibility", visibility);
      map.setPaintProperty(
        "corridor-heatmap-dots",
        "circle-opacity",
        heatmapOpacity * 0.7
      );
    }

    if (!heatmapEnabled || !heatmap) return;

    let colorExpr: maplibregl.ExpressionSpecification;
    if (heatmapLayer === "wind") {
      colorExpr = [
        "interpolate",
        ["linear"],
        ["get", "wind"],
        0,
        "#10b981",
        25,
        "#eab308",
        35,
        "#f97316",
        45,
        "#ef4444",
        55,
        "#991b1b",
      ];
    } else if (heatmapLayer === "rain") {
      colorExpr = [
        "interpolate",
        ["linear"],
        ["get", "rain"],
        0,
        "#0f172a",
        0.05,
        "#10b981",
        0.1,
        "#eab308",
        0.25,
        "#f97316",
        0.5,
        "#ef4444",
        1.0,
        "#991b1b",
      ];
    } else if (heatmapLayer === "snow") {
      colorExpr = [
        "interpolate",
        ["linear"],
        ["get", "snow"],
        0,
        "#0f172a",
        0.2,
        "#38bdf8",
        0.5,
        "#eab308",
        1.0,
        "#f97316",
        2.0,
        "#ef4444",
        3.0,
        "#991b1b",
      ];
    } else {
      colorExpr = [
        "interpolate",
        ["linear"],
        ["get", "risk"],
        0,
        "#10b981",
        1,
        "#eab308",
        2,
        "#f97316",
        3,
        "#ef4444",
        4,
        "#991b1b",
      ];
    }

    map.setPaintProperty("corridor-heatmap-glow", "circle-color", colorExpr);
    map.setPaintProperty("corridor-heatmap-dots", "circle-color", colorExpr);

    // Update GeoJSON data in-memory (0 network requests)
    source.setData(buildHeatmapGeoJSON(heatmap, sliderHour));
  }, [
    mapLoaded,
    heatmap,
    sliderHour,
    heatmapLayer,
    heatmapEnabled,
    heatmapOpacity,
  ]);

  // Update route lines when analysis or selectedRouteId changes (MP-1, MP-2)
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded || !analysis) return;

    const nonSelectedSource = map.getSource("non-selected-routes") as
      | maplibregl.GeoJSONSource
      | undefined;
    const selectedSource = map.getSource("selected-route-segments") as
      | maplibregl.GeoJSONSource
      | undefined;

    if (nonSelectedSource) {
      nonSelectedSource.setData(
        buildNonSelectedRoutesGeoJSON(
          analysis.routes,
          selectedRoute?.id ?? null
        )
      );
    }
    if (selectedSource) {
      selectedSource.setData(buildSelectedRouteSegmentsGeoJSON(selectedRoute));
    }
  }, [mapLoaded, analysis, selectedRoute]);

  // Fit bounds when a new analysis arrives
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded || !analysis || analysis.routes.length === 0) return;

    const bounds = new maplibregl.LngLatBounds();
    analysis.routes.forEach((route) => {
      route.coordinates.forEach(([lat, lng]) => {
        bounds.extend([lng, lat]);
      });
    });

    if (!bounds.isEmpty()) {
      map.fitBounds(bounds, {
        padding: { top: 60, bottom: 90, left: 60, right: 60 },
        duration: 900,
      });
    }
  }, [mapLoaded, analysis?.analysisId]);

  // Render Origin & Destination markers (MP-4)
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded) return;

    originDestMarkersRef.current.forEach((m) => m.remove());
    originDestMarkersRef.current = [];

    if (!analysis) return;

    const createEndpointElement = (
      label: string,
      name: string,
      isOrigin: boolean
    ) => {
      const el = document.createElement("div");
      el.className =
        "flex items-center gap-1.5 px-2.5 py-1 rounded-full shadow-lg border text-xs font-bold pointer-events-auto";
      el.style.backgroundColor = isOrigin ? "#064e3b" : "#1e1b4b";
      el.style.borderColor = isOrigin ? "#10b981" : "#6366f1";
      el.style.color = "#ffffff";
      el.innerHTML = `<span class="px-1.5 py-0.5 rounded bg-black/40 text-[10px] tracking-wider">${label}</span><span>${
        name.split(",")[0]
      }</span>`;
      return el;
    };

    const originEl = createEndpointElement(
      "ORIGIN",
      analysis.origin.label,
      true
    );
    const destEl = createEndpointElement(
      "DEST",
      analysis.destination.label,
      false
    );

    const originMarker = new maplibregl.Marker({
      element: originEl,
      anchor: "bottom",
    })
      .setLngLat([analysis.origin.lng, analysis.origin.lat])
      .addTo(map);
    const destMarker = new maplibregl.Marker({
      element: destEl,
      anchor: "bottom",
    })
      .setLngLat([analysis.destination.lng, analysis.destination.lat])
      .addTo(map);

    originDestMarkersRef.current.push(originMarker, destMarker);
  }, [mapLoaded, analysis]);

  // Render Checkpoint markers with distinct color + shape (MP-3, MP-5, MP-6)
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded) return;

    markersRef.current.forEach((m) => m.remove());
    markersRef.current = [];
    if (activePopupRef.current) {
      activePopupRef.current.remove();
      activePopupRef.current = null;
    }

    if (!selectedRoute) return;

    const openCheckpointPopup = (cp: RouteCheckpoint) => {
      if (activePopupRef.current) {
        activePopupRef.current.remove();
      }
      const color = RISK_COLORS[cp.level] ?? "#64748b";
      const shape = RISK_SHAPES[cp.level] ?? "?";
      const html = `
        <div class="p-3 min-w-[235px] text-slate-100 font-sans">
          <div class="flex items-center justify-between gap-2 border-b border-slate-700/80 pb-2 mb-2">
            <div>
              <div class="text-[11px] font-mono text-slate-400">CP #${
                cp.index
              } • Mile ${Math.round(cp.mile)}</div>
              <div class="text-sm font-bold text-white">${cp.place}</div>
            </div>
            <span class="px-2 py-0.5 rounded text-xs font-bold border" style="background:${color}33;color:#ffffff;border-color:${color}">
              ${shape} ${cp.level}
            </span>
          </div>
          <div class="text-xs text-slate-300 mb-2">
            <span class="text-slate-400">Local ETA:</span> <strong class="text-white">${
              cp.etaLocalDisplay
            }</strong>
          </div>
          <div class="grid grid-cols-2 gap-1.5 text-xs bg-slate-950/70 p-2 rounded border border-slate-800 mb-2">
            <div><span class="text-slate-400">Wind:</span> <strong class="text-white">${
              cp.weather.windMph !== null
                ? `${cp.weather.windMph.toFixed(1)} mph`
                : "—"
            }</strong></div>
            <div><span class="text-slate-400">Gust:</span> <strong class="text-amber-300">${
              cp.weather.gustMph !== null
                ? `${cp.weather.gustMph.toFixed(1)} mph`
                : "—"
            }</strong></div>
            <div><span class="text-slate-400">Rain:</span> <strong class="text-sky-300">${
              cp.weather.rainInHr !== null
                ? `${cp.weather.rainInHr.toFixed(2)} in/hr`
                : "—"
            }</strong></div>
            <div><span class="text-slate-400">Snow:</span> <strong class="text-indigo-200">${
              cp.weather.snowInHr !== null
                ? `${cp.weather.snowInHr.toFixed(2)} in/hr`
                : "—"
            }</strong></div>
            <div class="col-span-2"><span class="text-slate-400">Temp:</span> <strong class="text-white">${
              cp.weather.temperatureF !== null
                ? `${cp.weather.temperatureF.toFixed(0)}°F`
                : "—"
            }</strong></div>
          </div>
          ${
            cp.loadEscalated
              ? `<div class="text-[11px] px-2 py-1 rounded bg-amber-950/80 border border-amber-500/50 text-amber-200 font-semibold mb-1.5">
                   ⚡ Cargo load weight escalated wind risk to ${cp.level}
                 </div>`
              : ""
          }
          <ul class="text-[11px] text-slate-300 space-y-0.5 list-disc list-inside">
            ${cp.reasons.map((r) => `<li>${r}</li>`).join("")}
          </ul>
        </div>
      `;

      const popup = new maplibregl.Popup({
        closeButton: true,
        closeOnClick: false,
        maxWidth: "300px",
        offset: 14,
      })
        .setLngLat([cp.lng, cp.lat])
        .setHTML(html)
        .addTo(map);

      activePopupRef.current = popup;
    };

    selectedRoute.checkpoints.forEach((cp) => {
      const color = RISK_COLORS[cp.level] ?? "#64748b";
      const shape = RISK_SHAPES[cp.level] ?? "?";
      const isSelected = selectedCheckpoint?.index === cp.index;

      const el = document.createElement("button");
      el.type = "button";
      el.title = `${cp.place} (${cp.level})`;
      el.className =
        "flex items-center justify-center rounded-full shadow-md transition-transform focus:outline-none";
      const size = isSelected
        ? 26
        : cp.level === "No Travel" || cp.level === "Severe"
        ? 22
        : 18;
      el.style.width = `${size}px`;
      el.style.height = `${size}px`;
      el.style.backgroundColor = color;
      el.style.border = isSelected ? "3px solid #ffffff" : "2px solid #0f172a";
      el.style.color = "#ffffff";
      el.style.fontSize = isSelected ? "12px" : "10px";
      el.style.fontWeight = "700";
      el.style.zIndex = isSelected ? "30" : "10";
      el.textContent = shape;

      el.addEventListener("click", (e) => {
        e.stopPropagation();
        setSelectedCheckpoint(cp);
        openCheckpointPopup(cp);
      });

      const marker = new maplibregl.Marker({ element: el })
        .setLngLat([cp.lng, cp.lat])
        .addTo(map);

      markersRef.current.push(marker);

      if (isSelected) {
        openCheckpointPopup(cp);
        map.easeTo({ center: [cp.lng, cp.lat], duration: 500 });
      }
    });
  }, [mapLoaded, selectedRoute, selectedCheckpoint, setSelectedCheckpoint]);

  // Render Animated Truck Position Marker along the selected route at sliderHour (HM-8)
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapLoaded) return;

    if (!selectedRoute || !heatmap) {
      if (truckMarkerRef.current) {
        truckMarkerRef.current.remove();
        truckMarkerRef.current = null;
      }
      return;
    }

    const positions = heatmap.truckPositions[selectedRoute.id];
    const idx = Math.max(0, Math.min(48, Math.round(sliderHour)));
    const pos = positions?.[idx];

    if (!pos) return;

    if (!truckMarkerRef.current) {
      const el = document.createElement("div");
      el.className =
        "flex items-center gap-1 px-2 py-1 rounded-full bg-sky-500 text-slate-950 font-extrabold text-[11px] shadow-xl border-2 border-white pointer-events-none";
      el.innerHTML = `<span>🚚</span><span class="truck-label">+0h</span>`;
      truckMarkerRef.current = new maplibregl.Marker({
        element: el,
        anchor: "center",
      })
        .setLngLat([pos.lng, pos.lat])
        .addTo(map);
    } else {
      truckMarkerRef.current.setLngLat([pos.lng, pos.lat]);
      const labelEl = truckMarkerRef.current
        .getElement()
        .querySelector(".truck-label");
      if (labelEl) {
        labelEl.textContent = pos.arrived ? "Arrived" : `+${idx}h`;
      }
    }
  }, [mapLoaded, heatmap, selectedRoute, sliderHour]);

  return (
    <div className="relative w-full h-full min-h-[420px] bg-slate-950 overflow-hidden select-none rounded-xl border border-slate-800">
      <div ref={mapContainerRef} className="w-full h-full min-h-[420px]" />

      {/* Top-Left Overlay: Route Summary Pill */}
      {selectedRoute && (
        <div className="absolute top-3 left-3 z-10 flex flex-wrap items-center gap-2 pointer-events-auto">
          <div className="bg-slate-900/90 backdrop-blur-md border border-slate-700/80 rounded-lg px-3 py-1.5 shadow-lg flex items-center gap-2.5">
            <Navigation className="w-4 h-4 text-sky-400 shrink-0" />
            <div>
              <div className="text-xs font-bold text-white flex items-center gap-2">
                <span>{selectedRoute.label}</span>
                <span
                  className="px-1.5 py-0.5 rounded text-[10px] font-bold text-white"
                  style={{
                    backgroundColor: RISK_COLORS[selectedRoute.metrics.maxLevel],
                  }}
                >
                  {RISK_SHAPES[selectedRoute.metrics.maxLevel]}{" "}
                  {selectedRoute.metrics.maxLevel}
                </span>
              </div>
              <div className="text-[11px] text-slate-400 hidden sm:block">
                Click any checkpoint marker or alternate dashed route to inspect
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Top-Right Floating Map Layer Pill (Google Maps / Windy style quick switcher) */}
      <div className="absolute top-3 right-12 z-10 hidden sm:flex items-center gap-1 bg-slate-900/90 backdrop-blur-md border border-slate-700/80 rounded-lg p-1 shadow-lg pointer-events-auto">
        <button
          type="button"
          onClick={() => setHeatmapEnabled(!heatmapEnabled)}
          title={heatmapEnabled ? "Hide Corridor Heatmap" : "Show Corridor Heatmap"}
          className={`px-2 py-1 rounded text-[11px] font-semibold inline-flex items-center gap-1 transition ${
            heatmapEnabled
              ? "bg-sky-500/20 text-sky-300 border border-sky-500/40"
              : "text-slate-400 hover:text-white"
          }`}
        >
          {heatmapEnabled ? (
            <Eye className="w-3.5 h-3.5" />
          ) : (
            <EyeOff className="w-3.5 h-3.5" />
          )}
          <span>Heatmap</span>
        </button>

        {(
          [
            { id: "risk", label: "Risk", icon: <Flame className="w-3 h-3" /> },
            { id: "wind", label: "Wind", icon: <Wind className="w-3 h-3" /> },
            { id: "rain", label: "Rain", icon: <CloudRain className="w-3 h-3" /> },
            { id: "snow", label: "Snow", icon: <Snowflake className="w-3 h-3" /> },
          ] as const
        ).map((opt) => (
          <button
            key={opt.id}
            type="button"
            onClick={() => {
              setHeatmapEnabled(true);
              setHeatmapLayer(opt.id);
            }}
            className={`px-2 py-1 rounded text-[11px] font-medium inline-flex items-center gap-1 transition ${
              heatmapEnabled && heatmapLayer === opt.id
                ? "bg-sky-500 text-slate-950 font-bold shadow"
                : "text-slate-300 hover:text-white"
            }`}
          >
            {opt.icon}
            <span>{opt.label}</span>
          </button>
        ))}
      </div>

      {/* Bottom-Left Compact & Collapsible Map Legend (MP-8: Color + Shape + Active Layer Thresholds) */}
      <div className="absolute bottom-3 left-3 z-10 bg-slate-900/92 backdrop-blur-md border border-slate-700/80 rounded-lg p-2 shadow-xl max-w-md pointer-events-auto">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-1 flex-wrap">
            {ORDERED_LEVELS.map((lvl) => (
              <div
                key={lvl}
                className="flex items-center gap-1 px-1.5 py-0.5 rounded bg-slate-950/75 border border-slate-800 text-[10px]"
              >
                <span
                  className="w-3.5 h-3.5 rounded-full flex items-center justify-center text-[8px] font-bold text-white shrink-0"
                  style={{ backgroundColor: RISK_COLORS[lvl] }}
                >
                  {RISK_SHAPES[lvl]}
                </span>
                <span className="text-slate-200 font-medium">
                  {lvl === "No Travel"
                    ? "No Trvl"
                    : lvl === "Moderate"
                    ? "Mod"
                    : lvl === "Unknown"
                    ? "Unk"
                    : lvl}
                </span>
              </div>
            ))}
          </div>

          <button
            type="button"
            onClick={() => setShowLegendDetails(!showLegendDetails)}
            className="text-[10px] font-mono text-sky-300 bg-sky-950/70 hover:bg-sky-900/70 px-1.5 py-0.5 rounded border border-sky-800/60 inline-flex items-center gap-0.5 shrink-0"
          >
            <span>{heatmapLayer.toUpperCase()}</span>
            {showLegendDetails ? (
              <ChevronDown className="w-3 h-3" />
            ) : (
              <ChevronUp className="w-3 h-3" />
            )}
          </button>
        </div>

        {showLegendDetails && (
          <div className="mt-1.5 pt-1.5 border-t border-slate-800/80 flex flex-wrap items-center justify-between gap-2 text-[10px] text-slate-400">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-300 flex items-center gap-1">
              <Layers className="w-3 h-3 text-sky-400" />
              <span>Risk & Checkpoint Legend (Color + Shape)</span>
            </span>
            {heatmapLayer === "risk" && (
              <span className="flex items-center gap-1">
                <ShieldAlert className="w-3 h-3 text-amber-400" />
                Overall Risk (0=Low → 4=No Travel, load-adjusted)
              </span>
            )}
            {heatmapLayer === "wind" && (
              <span className="flex items-center gap-1">
                <Wind className="w-3 h-3 text-sky-400" />
                Wind/Gust: &lt;25 Low • 25–35 Mod • 35–45 High • 45–55 Sev • ≥55
                mph No Travel
              </span>
            )}
            {heatmapLayer === "rain" && (
              <span className="flex items-center gap-1">
                <CloudRain className="w-3 h-3 text-sky-400" />
                Rain: &lt;0.10 Low • 0.10–0.25 Mod • &gt;0.25–0.50 High •
                &gt;0.50–1.00 Sev • &gt;1.00 in/hr No Travel
              </span>
            )}
            {heatmapLayer === "snow" && (
              <span className="flex items-center gap-1">
                <Snowflake className="w-3 h-3 text-sky-400" />
                Snow: &lt;0.5 Low • 0.5–1.0 Mod • &gt;1.0–2.0 High • &gt;2.0–3.0
                Sev • &gt;3.0 in/hr No Travel
              </span>
            )}
            <span className="text-slate-300 font-medium">
              🚚 Truck position at +{sliderHour}h
            </span>
          </div>
        )}
      </div>
    </div>
  );
};
