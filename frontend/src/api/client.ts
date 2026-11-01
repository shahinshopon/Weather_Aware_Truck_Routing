import type {
  AnalysisResponse,
  AnalyzeRequestPayload,
  DepartureWindowResponse,
  GeocodeLocation,
  HeatmapResponse,
} from "../types/api";

const API_BASE = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let errMessage = `Request failed with status ${res.status}`;
    try {
      const errBody = await res.json();
      if (errBody?.error) {
        errMessage = errBody.error;
      }
    } catch {
      // ignore json parse error
    }
    throw new Error(errMessage);
  }
  return res.json() as Promise<T>;
}

export async function fetchGeocodeSuggestions(
  query: string
): Promise<GeocodeLocation[]> {
  if (query.trim().length < 2) return [];
  const url = `${API_BASE}/api/v1/geocode/?q=${encodeURIComponent(
    query.trim()
  )}`;
  const res = await fetch(url);
  const data = await handleResponse<{ results: GeocodeLocation[] }>(res);
  return data.results ?? [];
}

export async function postAnalyzeTrip(
  payload: AnalyzeRequestPayload
): Promise<AnalysisResponse> {
  const res = await fetch(`${API_BASE}/api/v1/analyze/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handleResponse<AnalysisResponse>(res);
}

export async function fetchCorridorHeatmap(
  analysisId: string
): Promise<HeatmapResponse> {
  const res = await fetch(
    `${API_BASE}/api/v1/analyze/${encodeURIComponent(analysisId)}/heatmap/`
  );
  return handleResponse<HeatmapResponse>(res);
}

export async function fetchDepartureWindow(
  analysisId: string
): Promise<DepartureWindowResponse> {
  const res = await fetch(
    `${API_BASE}/api/v1/analyze/${encodeURIComponent(
      analysisId
    )}/departure-window/`
  );
  return handleResponse<DepartureWindowResponse>(res);
}
