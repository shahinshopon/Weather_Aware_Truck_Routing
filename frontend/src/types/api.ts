export type RiskLevelLabel =
  | "Low"
  | "Moderate"
  | "High"
  | "Severe"
  | "No Travel"
  | "Unknown";

export type HeatmapLayerMode = "risk" | "wind" | "rain" | "snow";

export interface GeocodeLocation {
  label: string;
  lat: number;
  lng: number;
  state?: string;
  country?: string;
}

export interface CheckpointWeather {
  windMph: number | null;
  gustMph: number | null;
  rainInHr: number | null;
  snowInHr: number | null;
  temperatureF: number | null;
  precipProbPct: number | null;
}

export interface RouteCheckpoint {
  index: number;
  mile: number;
  lat: number;
  lng: number;
  place: string;
  segmentMiles: number;
  etaUtc: string;
  etaLocal: string;
  etaLocalDisplay: string;
  timezoneAbbr: string;
  etaIsEstimate: boolean;
  weather: CheckpointWeather;
  level: RiskLevelLabel;
  score: number;
  drivingCondition: string;
  loadEscalated: boolean;
  reasons: string[];
  dataQuality: "ok" | "borrowed" | "unknown";
}

export interface RiskSegment {
  checkpointIndex: number;
  startMile: number;
  endMile: number;
  level: RiskLevelLabel;
  score: number;
  coordinates: [number, number][]; // [lng, lat][]
}

export interface RouteTradeoff {
  timeAddedMin: number;
  severeMilesSaved: number;
  highMilesSaved: number;
  noTravelMilesSaved: number;
  isFastest: boolean;
  summary: string;
}

export interface RouteMetrics {
  totalMiles: number;
  durationMin: number;
  milesByLevel: Record<RiskLevelLabel, number>;
  lowMiles: number;
  moderateMiles: number;
  highMiles: number;
  severeMiles: number;
  noTravelMiles: number;
  unknownMiles: number;
  avgRisk: number;
  maxLevel: RiskLevelLabel;
  maxLevelScore: number;
  worstCheckpoint: {
    index: number;
    mile: number;
    place: string;
    reason: string;
  };
  noTravelCheckpointCount: number;
  hasUnknownWeather: boolean;
}

export interface AnalyzedRoute {
  id: string;
  label: string;
  summary: string;
  encodedGeometry: string;
  coordinates: [number, number][]; // [lat, lng][]
  distanceMi: number;
  durationMin: number;
  arrivalTimeUtc: string;
  arrivalTimeLocal: string;
  rank: number;
  recommended: boolean;
  blocked: boolean;
  blockedReason: string | null;
  metrics: RouteMetrics;
  tradeoff: RouteTradeoff;
  riskSegments: RiskSegment[];
  checkpoints: RouteCheckpoint[];
}

export interface RecommendationInfo {
  recommendedRouteId: string | null;
  recommendedRouteLabel: string | null;
  allBlocked: boolean;
  leastBadRouteId: string | null;
  headline: string;
  explanation: string;
  reasons: string[];
}

export interface AnalysisResponse {
  analysisId: string;
  origin: GeocodeLocation;
  destination: GeocodeLocation;
  departureTimeUtc: string;
  departureTimeLocalDisplay: string;
  originTimezone: string;
  originTimezoneAbbr: string;
  loadWeightLb: number;
  intervalMiles: 10 | 25 | 50;
  options: {
    gustAware: boolean;
    demoScenario: string | null;
  };
  recommendedRouteId: string | null;
  leastBadRouteId: string | null;
  allBlocked: boolean;
  recommendation: RecommendationInfo;
  warnings: string[];
  forecastIssuedAt: string;
  forecastSource: string;
  routes: AnalyzedRoute[];
}

export interface HeatmapCell {
  id: string;
  lat: number;
  lng: number;
  offsetMiles: number;
  routeIds: string[];
  risk: number[]; // 49 values (0..4)
  wind: number[]; // 49 values (mph)
  rain: number[]; // 49 values (in/hr)
  snow: number[]; // 49 values (in/hr)
}

export interface TruckHourlyPosition {
  hour: number;
  inTransit: boolean;
  arrived: boolean;
  lat: number;
  lng: number;
  mile: number;
  place: string;
  localTime: string;
  level: RiskLevelLabel;
  score: number;
  windMph: number | null;
  rainInHr: number | null;
  snowInHr: number | null;
  reason: string;
}

export interface HeatmapResponse {
  analysisId: string;
  departureTimeUtc: string;
  forecastIssuedAt: string;
  forecastSource: string;
  loadWeightLb: number;
  corridorBufferMiles: number;
  cellCount: number;
  hours: number[];
  hourLabels: string[];
  cells: HeatmapCell[];
  truckPositions: Record<string, TruckHourlyPosition[]>;
}

export interface DepartureWindowItem {
  offsetHours: number;
  departureTimeUtc: string;
  departureTimeLocal: string;
  allBlocked: boolean;
  bestRouteId: string;
  bestRouteLabel: string;
  noTravelMiles: number;
  severeMiles: number;
  highMiles: number;
  avgRisk: number;
  durationMin: number;
}

export interface DepartureWindowResponse {
  analysisId: string;
  recommendedOffsetHours: number;
  recommendedDepartureLocal: string;
  suggestion: string;
  windows: DepartureWindowItem[];
}

export interface AnalyzeRequestPayload {
  origin: GeocodeLocation;
  destination: GeocodeLocation;
  departureTime: string;
  loadWeightLb: number;
  intervalMiles: 10 | 25 | 50;
  options: {
    gustAware: boolean;
    demoScenario: string | null;
  };
}
