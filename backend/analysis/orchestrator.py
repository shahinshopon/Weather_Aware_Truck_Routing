"""Orchestrates geocoding, routing, checkpoint generation, weather grid fetch, risk classification, route scoring, 0-48h heatmap payload, and departure window scanning."""

from __future__ import annotations

import uuid
from dataclasses import asdict
from datetime import UTC, datetime, timedelta

from django.core.cache import cache

from geocoding.service import nearest_place_label, resolve_place
from geometry.checkpoints import (
    CheckpointGeometry,
    build_corridor_grid,
    compute_cumulative_miles,
    format_local_eta,
    generate_checkpoints,
    haversine_miles,
    interpolate_point_at_mile,
    point_at_elapsed_minutes,
    snap_to_grid,
)
from risk.config import LOAD_SOFT_WARNING_LB
from risk.engine import classify_checkpoint_risk
from routing.service import RawRouteCandidate, generate_truck_routes
from scoring.scorer import (
    EvaluatedCheckpoint,
    ScoredRoute,
    compute_route_metrics,
    rank_and_recommend_routes,
)
from weather.service import (
    GridForecastSeries,
    fetch_grid_forecasts,
    interpolate_weather_at_eta,
    sample_checkpoint_weather_with_fallback,
)

ANALYSIS_CACHE_TTL_SECONDS = 3600  # 1 hour TTL (Section 4.11)


class AnalysisError(Exception):
    """Domain validation or routing failure error."""

    def __init__(self, message: str, status_code: int = 400, field_errors: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.field_errors = field_errors or {}


def _build_route_risk_segments(
    coords: list[tuple[float, float]],
    checkpoints: list[EvaluatedCheckpoint],
    total_miles: float,
) -> list[dict[str, object]]:
    """
    MP-2: Slice route polyline into risk-colored GeoJSON-ready line segments corresponding
    to each checkpoint's owned stretch (midpoint to previous checkpoint -> midpoint to next).
    """
    if not coords or not checkpoints:
        return []

    raw_cum = compute_cumulative_miles(coords)
    raw_total = raw_cum[-1] if raw_cum else 0.0
    scale = (total_miles / raw_total) if (raw_total > 1e-6 and total_miles > 0) else 1.0
    cum_miles = [m * scale for m in raw_cum]

    segments: list[dict[str, object]] = []
    n = len(checkpoints)

    for i, cp in enumerate(checkpoints):
        start_m = 0.0 if i == 0 else 0.5 * (checkpoints[i - 1].mile + cp.mile)
        end_m = total_miles if i == n - 1 else 0.5 * (cp.mile + checkpoints[i + 1].mile)
        if end_m <= start_m + 1e-4 and n > 1:
            continue

        # Collect polyline points between start_m and end_m
        seg_pts: list[list[float]] = []
        p_start = interpolate_point_at_mile(coords, cum_miles, start_m)
        seg_pts.append([p_start[1], p_start[0]])  # GeoJSON [lng, lat]

        for v_idx, v_mile in enumerate(cum_miles):
            if start_m < v_mile < end_m:
                seg_pts.append([coords[v_idx][1], coords[v_idx][0]])

        p_end = interpolate_point_at_mile(coords, cum_miles, end_m)
        if not seg_pts or seg_pts[-1] != [p_end[1], p_end[0]]:
            seg_pts.append([p_end[1], p_end[0]])

        if len(seg_pts) == 1:
            seg_pts.append(seg_pts[0])

        segments.append(
            {
                "checkpointIndex": cp.index,
                "startMile": round(start_m, 1),
                "endMile": round(end_m, 1),
                "level": cp.label,
                "score": cp.score,
                "coordinates": seg_pts,  # [[lng, lat], ...]
            }
        )

    return segments


def _evaluate_route_for_departure(
    raw_route: RawRouteCandidate,
    departure_utc: datetime,
    interval_miles: int,
    load_weight_lb: float,
    gust_aware: bool,
    grid_map: dict[tuple[float, float], GridForecastSeries],
    origin_label: str,
    dest_label: str,
    precomputed_geom_checkpoints: list[CheckpointGeometry] | None = None,
) -> tuple[ScoredRoute, bool]:
    """Evaluate a single route candidate at a given departure time against the cached weather grid."""
    geom_cps = (
        precomputed_geom_checkpoints
        if precomputed_geom_checkpoints is not None
        else generate_checkpoints(
            coords=raw_route.coordinates,
            departure_utc=departure_utc,
            interval_miles=float(interval_miles),
            total_duration_seconds=raw_route.duration_seconds,
            sections=raw_route.sections,
            override_total_miles=raw_route.distance_mi,
        )
    )

    cp_coords_and_etas = [(cp.lat, cp.lng, cp.eta_utc) for cp in geom_cps]
    weather_samples, has_degraded = sample_checkpoint_weather_with_fallback(
        cp_coords_and_etas, grid_map
    )

    evaluated_cps: list[EvaluatedCheckpoint] = []
    n_cps = len(geom_cps)

    for idx, (gcp, wx) in enumerate(zip(geom_cps, weather_samples, strict=True)):
        risk_res = classify_checkpoint_risk(
            wx, load_weight_lb, gust_aware=gust_aware
        )
        if idx == 0 and origin_label:
            place_str = f"Origin · {origin_label}"
        elif idx == n_cps - 1 and dest_label:
            place_str = f"Destination · {dest_label}"
        else:
            place_str = nearest_place_label(gcp.lat, gcp.lng, gcp.mile)

        evaluated_cps.append(
            EvaluatedCheckpoint(
                index=gcp.index,
                mile=gcp.mile,
                lat=gcp.lat,
                lng=gcp.lng,
                place=place_str,
                segment_miles=round(gcp.segment_miles, 2),
                eta_utc_iso=gcp.eta_utc.isoformat(),
                eta_local_iso=gcp.eta_local_iso,
                eta_local_display=gcp.eta_local_display,
                timezone_abbr=gcp.timezone_abbr,
                eta_is_estimate=gcp.eta_is_estimate,
                wind_mph=wx.wind_mph,
                gust_mph=wx.gust_mph,
                rain_in_hr=wx.rain_in_hr,
                snow_in_hr=wx.snow_in_hr,
                temperature_f=wx.temperature_f,
                precip_prob_pct=wx.precip_prob_pct,
                level=risk_res.level,
                label=risk_res.label,
                score=risk_res.score,
                driving_condition=risk_res.driving_condition,
                load_escalated=risk_res.load_escalated,
                reasons=risk_res.reasons,
                data_quality=risk_res.data_quality,
            )
        )

    metrics = compute_route_metrics(
        evaluated_cps, raw_route.distance_mi, raw_route.duration_min
    )
    last_cp = evaluated_cps[-1]
    risk_segments = _build_route_risk_segments(
        raw_route.coordinates, evaluated_cps, raw_route.distance_mi
    )

    scored_route = ScoredRoute(
        id=raw_route.id,
        label=raw_route.label,
        summary=raw_route.summary,
        encoded_geometry=raw_route.encoded_geometry,
        coordinates=raw_route.coordinates,
        distance_mi=raw_route.distance_mi,
        duration_min=raw_route.duration_min,
        arrival_time_utc=last_cp.eta_utc_iso,
        arrival_time_local=last_cp.eta_local_display,
        checkpoints=evaluated_cps,
        metrics=metrics,
        blocked=metrics.no_travel_miles > 0.0,
        risk_segments=risk_segments,
    )
    return scored_route, has_degraded


def _serialize_route(route: ScoredRoute) -> dict[str, object]:
    """Serialize ScoredRoute into the exact camelCase API contract (Section 5.2)."""
    return {
        "id": route.id,
        "label": route.label,
        "summary": route.summary,
        "encodedGeometry": route.encoded_geometry,
        "coordinates": [[lat, lng] for lat, lng in route.coordinates],
        "distanceMi": route.distance_mi,
        "durationMin": route.duration_min,
        "arrivalTimeUtc": route.arrival_time_utc,
        "arrivalTimeLocal": route.arrival_time_local,
        "rank": route.rank,
        "recommended": route.recommended,
        "blocked": route.blocked,
        "blockedReason": route.blocked_reason,
        "metrics": {
            "totalMiles": route.metrics.total_miles,
            "durationMin": route.metrics.duration_min,
            "milesByLevel": route.metrics.miles_by_level,
            "lowMiles": route.metrics.low_miles,
            "moderateMiles": route.metrics.moderate_miles,
            "highMiles": route.metrics.high_miles,
            "severeMiles": route.metrics.severe_miles,
            "noTravelMiles": route.metrics.no_travel_miles,
            "unknownMiles": route.metrics.unknown_miles,
            "avgRisk": route.metrics.avg_risk,
            "maxLevel": route.metrics.max_level_label,
            "maxLevelScore": int(route.metrics.max_level),
            "worstCheckpoint": {
                "index": route.metrics.worst_checkpoint_index,
                "mile": route.metrics.worst_checkpoint_mile,
                "place": route.metrics.worst_checkpoint_place,
                "reason": route.metrics.worst_checkpoint_reason,
            },
            "noTravelCheckpointCount": route.metrics.no_travel_checkpoint_count,
            "hasUnknownWeather": route.metrics.has_unknown_weather,
        },
        "tradeoff": {
            "timeAddedMin": route.tradeoff.time_added_min if route.tradeoff else 0,
            "severeMilesSaved": route.tradeoff.severe_miles_saved if route.tradeoff else 0.0,
            "highMilesSaved": route.tradeoff.high_miles_saved if route.tradeoff else 0.0,
            "noTravelMilesSaved": route.tradeoff.no_travel_miles_saved if route.tradeoff else 0.0,
            "isFastest": route.tradeoff.is_fastest if route.tradeoff else False,
            "summary": route.tradeoff.summary if route.tradeoff else "",
        },
        "riskSegments": route.risk_segments,
        "checkpoints": [
            {
                "index": cp.index,
                "mile": cp.mile,
                "lat": cp.lat,
                "lng": cp.lng,
                "place": cp.place,
                "segmentMiles": cp.segment_miles,
                "etaUtc": cp.eta_utc_iso,
                "etaLocal": cp.eta_local_iso,
                "etaLocalDisplay": cp.eta_local_display,
                "timezoneAbbr": cp.timezone_abbr,
                "etaIsEstimate": cp.eta_is_estimate,
                "weather": {
                    "windMph": cp.wind_mph,
                    "gustMph": cp.gust_mph,
                    "rainInHr": cp.rain_in_hr,
                    "snowInHr": cp.snow_in_hr,
                    "temperatureF": cp.temperature_f,
                    "precipProbPct": cp.precip_prob_pct,
                },
                "level": cp.label,
                "score": cp.score,
                "drivingCondition": cp.driving_condition,
                "loadEscalated": cp.load_escalated,
                "reasons": cp.reasons,
                "dataQuality": cp.data_quality,
            }
            for cp in route.checkpoints
        ],
    }


def run_trip_analysis(
    origin_input: dict[str, object],
    destination_input: dict[str, object],
    departure_time_iso: str,
    load_weight_lb: float,
    interval_miles: int = 25,
    options: dict[str, object] | None = None,
) -> dict[str, object]:
    """
    POST /api/v1/analyze/ orchestrator:
    1. Validate and resolve Origin and Destination (GC-3)
    2. Validate Departure Time and Load Weight (IN-2, IN-3)
    3. Generate up to 3 distinct truck routes (RT-1 to RT-5)
    4. Generate checkpoints every N miles (CP-1 to CP-5)
    5. Batch-fetch grid-snapped weather for all checkpoints (WX-1 to WX-4)
    6. Classify risk and load rules (RK-1 to RK-6)
    7. Score, rank, and build plain-language recommendation (SC-1 to SC-5)
    8. Store temporary analysis context in cache (1h TTL) for heatmap & departure window
    """
    opts = options or {}
    gust_aware = bool(opts.get("gustAware", False))
    demo_scenario = str(opts.get("demoScenario") or "").strip() or None

    # Validate load weight (IN-3)
    if load_weight_lb <= 0:
        raise AnalysisError(
            "Load weight must be greater than 0 lb.",
            status_code=400,
            field_errors={"loadWeightLb": "Must be greater than 0 lb."},
        )

    # Validate interval (IN-4)
    if interval_miles not in (10, 25, 50):
        raise AnalysisError(
            "Checkpoint interval must be 10, 25, or 50 miles.",
            status_code=400,
            field_errors={"intervalMiles": "Allowed values are 10, 25, or 50."},
        )

    # Resolve Origin and Destination (GC-3)
    origin_place = resolve_place(
        label=str(origin_input.get("label") or ""),
        lat=float(origin_input["lat"]) if origin_input.get("lat") is not None else None,  # type: ignore[arg-type]
        lng=float(origin_input["lng"]) if origin_input.get("lng") is not None else None,  # type: ignore[arg-type]
    )
    dest_place = resolve_place(
        label=str(destination_input.get("label") or ""),
        lat=float(destination_input["lat"]) if destination_input.get("lat") is not None else None,  # type: ignore[arg-type]
        lng=float(destination_input["lng"]) if destination_input.get("lng") is not None else None,  # type: ignore[arg-type]
    )

    if origin_place is None:
        raise AnalysisError(
            "Could not locate the origin address. Please select a valid US location.",
            status_code=400,
            field_errors={"origin": "Origin location not found."},
        )
    if dest_place is None:
        raise AnalysisError(
            "Could not locate the destination address. Please select a valid US location.",
            status_code=400,
            field_errors={"destination": "Destination location not found."},
        )

    dist_origin_dest = haversine_miles(
        origin_place.lat, origin_place.lng, dest_place.lat, dest_place.lng
    )
    if dist_origin_dest < 0.5:
        raise AnalysisError(
            "Origin and destination cannot be the same location.",
            status_code=400,
            field_errors={"destination": "Destination must be distinct from origin."},
        )

    # Parse departure time (IN-2)
    try:
        dep_dt = datetime.fromisoformat(departure_time_iso.replace("Z", "+00:00"))
        if dep_dt.tzinfo is None:
            dep_dt = dep_dt.replace(tzinfo=UTC)
        else:
            dep_dt = dep_dt.astimezone(UTC)
    except Exception as exc:
        raise AnalysisError(
            "Invalid departureTime format. Expected ISO 8601 datetime string.",
            status_code=400,
            field_errors={"departureTime": "Invalid ISO 8601 timestamp."},
        ) from exc

    warnings: list[str] = []
    if load_weight_lb > LOAD_SOFT_WARNING_LB:
        warnings.append(
            f"Cargo load weight ({load_weight_lb:,.0f} lb) exceeds 80,000 lb (typical US gross vehicle weight limit). Proceeding with entered cargo weight."
        )

    # Generate up to 3 distinct truck routes
    routing_res = generate_truck_routes(
        origin=(origin_place.lat, origin_place.lng),
        destination=(dest_place.lat, dest_place.lng),
        origin_label=origin_place.label,
        destination_label=dest_place.label,
        load_weight_lb=load_weight_lb,
    )
    warnings.extend(routing_res.warnings)

    if not routing_res.routes:
        raise AnalysisError(
            "No drivable truck routes were found between the selected origin and destination. Please verify both locations are reachable by road.",
            status_code=422,
        )

    # Pre-generate checkpoint geometries for each route so we can batch-fetch weather in one call
    route_geom_cps: dict[str, list[CheckpointGeometry]] = {}
    all_checkpoint_coords: list[tuple[float, float]] = []

    for r_cand in routing_res.routes:
        cps = generate_checkpoints(
            coords=r_cand.coordinates,
            departure_utc=dep_dt,
            interval_miles=float(interval_miles),
            total_duration_seconds=r_cand.duration_seconds,
            sections=r_cand.sections,
            override_total_miles=r_cand.distance_mi,
        )
        route_geom_cps[r_cand.id] = cps
        for cp in cps:
            all_checkpoint_coords.append((cp.lat, cp.lng))

    grid_map, forecast_issued_at, forecast_source = fetch_grid_forecasts(
        all_checkpoint_coords,
        dep_dt,
        demo_scenario=demo_scenario,
    )

    scored_routes: list[ScoredRoute] = []
    any_degraded_weather = False

    for r_cand in routing_res.routes:
        s_route, has_deg = _evaluate_route_for_departure(
            raw_route=r_cand,
            departure_utc=dep_dt,
            interval_miles=interval_miles,
            load_weight_lb=load_weight_lb,
            gust_aware=gust_aware,
            grid_map=grid_map,
            origin_label=origin_place.label,
            dest_label=dest_place.label,
            precomputed_geom_checkpoints=route_geom_cps[r_cand.id],
        )
        scored_routes.append(s_route)
        if has_deg or s_route.metrics.has_unknown_weather:
            any_degraded_weather = True

    if any_degraded_weather:
        warnings.append(
            "Partial weather data: one or more checkpoints had unavailable forecast data and borrowed nearest-neighbor values or were flagged Unknown."
        )

    ranked_routes, rec_summary = rank_and_recommend_routes(scored_routes)

    analysis_id = str(uuid.uuid4())
    _, dep_local_display, dep_tz_name, dep_tz_abbr = format_local_eta(
        dep_dt, origin_place.lat, origin_place.lng
    )

    # Store context in cache (1h TTL) for lazy heatmap & departure-window endpoints
    cached_context = {
        "analysis_id": analysis_id,
        "origin": asdict(origin_place),
        "destination": asdict(dest_place),
        "departure_utc": dep_dt,
        "load_weight_lb": load_weight_lb,
        "interval_miles": interval_miles,
        "gust_aware": gust_aware,
        "demo_scenario": demo_scenario,
        "raw_routes": routing_res.routes,
        "ranked_route_ids": [r.id for r in ranked_routes],
        "recommended_route_id": rec_summary.recommended_route_id or rec_summary.least_bad_route_id,
        "forecast_issued_at": forecast_issued_at,
        "forecast_source": forecast_source,
    }
    cache.set(f"analysis:ctx:{analysis_id}", cached_context, timeout=ANALYSIS_CACHE_TTL_SECONDS)

    return {
        "analysisId": analysis_id,
        "origin": {
            "label": origin_place.label,
            "lat": origin_place.lat,
            "lng": origin_place.lng,
        },
        "destination": {
            "label": dest_place.label,
            "lat": dest_place.lat,
            "lng": dest_place.lng,
        },
        "departureTimeUtc": dep_dt.isoformat(),
        "departureTimeLocalDisplay": dep_local_display,
        "originTimezone": dep_tz_name,
        "originTimezoneAbbr": dep_tz_abbr,
        "loadWeightLb": load_weight_lb,
        "intervalMiles": interval_miles,
        "options": {
            "gustAware": gust_aware,
            "demoScenario": demo_scenario,
        },
        "recommendedRouteId": rec_summary.recommended_route_id,
        "leastBadRouteId": rec_summary.least_bad_route_id,
        "allBlocked": rec_summary.all_blocked,
        "recommendation": {
            "recommendedRouteId": rec_summary.recommended_route_id,
            "recommendedRouteLabel": rec_summary.recommended_route_label,
            "allBlocked": rec_summary.all_blocked,
            "leastBadRouteId": rec_summary.least_bad_route_id,
            "headline": rec_summary.headline,
            "explanation": rec_summary.explanation,
            "reasons": rec_summary.reasons,
        },
        "warnings": warnings,
        "forecastIssuedAt": forecast_issued_at,
        "forecastSource": forecast_source,
        "routes": [_serialize_route(r) for r in ranked_routes],
    }


def build_heatmap_payload(analysis_id: str) -> dict[str, object]:
    """
    GET /api/v1/analyze/{id}/heatmap/ (PRD Section 4.9, HM-1 to HM-9):
    Builds a compact 49-hour (hours 0..48 relative to departure) weather and risk grid
    across the union corridor of the three routes buffered by ~25 miles each side.
    Applies the exact same risk engine and load rules (HM-7) so heatmap and checkpoint
    colors never contradict each other.
    Also precomputes hourly truck positions along each route for HM-8.
    """
    payload_cache_key = f"analysis:heatmap:{analysis_id}"
    cached_payload = cache.get(payload_cache_key)
    if cached_payload is not None:
        return dict(cached_payload)

    ctx = cache.get(f"analysis:ctx:{analysis_id}")
    if ctx is None:
        raise AnalysisError(
            "Analysis session expired or not found. Please re-run the route analysis.",
            status_code=404,
        )

    dep_dt: datetime = ctx["departure_utc"]
    load_weight_lb: float = float(ctx["load_weight_lb"])
    gust_aware: bool = bool(ctx["gust_aware"])
    demo_scenario: str | None = ctx["demo_scenario"]
    raw_routes: list[RawRouteCandidate] = ctx["raw_routes"]
    origin_info: dict[str, object] = ctx["origin"]

    route_geoms = [(r.id, r.coordinates) for r in raw_routes]
    corridor_cells = build_corridor_grid(
        routes=route_geoms,
        step_miles=12.0,
        lateral_offsets_miles=(0.0, -13.0, 13.0, -25.0, 25.0),
        max_cells=1400,
        grid_resolution_deg=0.1,
    )

    # Precompute hourly truck coordinates across routes so their snapped 0.1° grid cells
    # are always included in fetch_grid_forecasts
    hourly_route_points: dict[str, list[tuple[float, float, float, bool]]] = {}
    extra_truck_coords: list[tuple[float, float]] = []
    for r in raw_routes:
        pts: list[tuple[float, float, float, bool]] = []
        for h_idx in range(49):
            elapsed_min = h_idx * 60.0
            in_transit = elapsed_min <= r.duration_min
            lat, lng, mile = point_at_elapsed_minutes(
                r.coordinates, float(r.duration_min), elapsed_min
            )
            pts.append((lat, lng, mile, in_transit))
            extra_truck_coords.append(snap_to_grid(lat, lng, 0.1))
        hourly_route_points[r.id] = pts

    cell_coords = list(
        dict.fromkeys(
            [(c.grid_lat, c.grid_lng) for c in corridor_cells] + extra_truck_coords
        )
    )
    grid_map, issued_at, source_name = fetch_grid_forecasts(
        cell_coords,
        dep_dt,
        demo_scenario=demo_scenario,
    )

    # Precompute 49 hourly timestamps (hours 0..48 relative to departure_utc)
    hour_timestamps: list[datetime] = [
        dep_dt + timedelta(hours=h) for h in range(49)
    ]
    hour_labels: list[str] = []
    origin_lat = float(origin_info["lat"])  # type: ignore[arg-type]
    origin_lng = float(origin_info["lng"])  # type: ignore[arg-type]
    for ts in hour_timestamps:
        _, local_disp, _, _ = format_local_eta(ts, origin_lat, origin_lng)
        hour_labels.append(local_disp)

    serialized_cells: list[dict[str, object]] = []
    for cell in corridor_cells:
        series = grid_map.get((cell.grid_lat, cell.grid_lng))
        risk_scores: list[int] = []
        wind_vals: list[float] = []
        rain_vals: list[float] = []
        snow_vals: list[float] = []

        for ts in hour_timestamps:
            wx = interpolate_weather_at_eta(series, ts)
            if wx is None:
                risk_scores.append(0)
                wind_vals.append(0.0)
                rain_vals.append(0.0)
                snow_vals.append(0.0)
            else:
                res = classify_checkpoint_risk(wx, load_weight_lb, gust_aware=gust_aware)
                risk_scores.append(max(0, res.score))
                wind_vals.append(round(res.effective_wind_mph or wx.wind_mph or 0.0, 1))
                rain_vals.append(round(wx.rain_in_hr or 0.0, 2))
                snow_vals.append(round(wx.snow_in_hr or 0.0, 2))

        serialized_cells.append(
            {
                "id": cell.cell_id,
                "lat": cell.lat,
                "lng": cell.lng,
                "offsetMiles": cell.offset_miles,
                "routeIds": list(cell.route_ids),
                "risk": risk_scores,  # 49 integers (0..4)
                "wind": wind_vals,    # 49 floats (mph)
                "rain": rain_vals,    # 49 floats (in/hr)
                "snow": snow_vals,    # 49 floats (in/hr)
            }
        )

    # HM-8: Precompute hourly truck position and risk on each route for hours 0..48
    truck_positions_by_route: dict[str, list[dict[str, object]]] = {}
    for r in raw_routes:
        positions: list[dict[str, object]] = []
        pts = hourly_route_points[r.id]
        for h_idx, ts in enumerate(hour_timestamps):
            elapsed_min = h_idx * 60.0
            lat, lng, mile, in_transit = pts[h_idx]
            g_key = snap_to_grid(lat, lng, 0.1)
            wx = interpolate_weather_at_eta(grid_map.get(g_key), ts)
            risk_res = classify_checkpoint_risk(wx, load_weight_lb, gust_aware=gust_aware)
            _, local_disp, _, _ = format_local_eta(ts, lat, lng)
            positions.append(
                {
                    "hour": h_idx,
                    "inTransit": in_transit,
                    "arrived": elapsed_min >= r.duration_min,
                    "lat": round(lat, 5),
                    "lng": round(lng, 5),
                    "mile": mile,
                    "place": nearest_place_label(lat, lng, mile),
                    "localTime": local_disp,
                    "level": risk_res.label,
                    "score": max(0, risk_res.score),
                    "windMph": wx.wind_mph if wx else None,
                    "rainInHr": wx.rain_in_hr if wx else None,
                    "snowInHr": wx.snow_in_hr if wx else None,
                    "reason": risk_res.reasons[0] if risk_res.reasons else "",
                }
            )
        truck_positions_by_route[r.id] = positions

    result = {
        "analysisId": analysis_id,
        "departureTimeUtc": dep_dt.isoformat(),
        "forecastIssuedAt": issued_at,
        "forecastSource": source_name,
        "loadWeightLb": load_weight_lb,
        "corridorBufferMiles": 25,
        "cellCount": len(serialized_cells),
        "hours": list(range(49)),
        "hourLabels": hour_labels,
        "cells": serialized_cells,
        "truckPositions": truck_positions_by_route,
    }
    cache.set(payload_cache_key, result, timeout=ANALYSIS_CACHE_TTL_SECONDS)
    return result


def build_departure_window_scan(analysis_id: str) -> dict[str, object]:
    """
    GET /api/v1/analyze/{id}/departure-window/ (PRD SC-6):
    Re-score the same routes for departures within -6h to +12h in 1h steps using the
    already cached 48h forecast, and suggest a safer departure time.
    """
    scan_cache_key = f"analysis:depscan:{analysis_id}"
    cached_scan = cache.get(scan_cache_key)
    if cached_scan is not None:
        return dict(cached_scan)

    ctx = cache.get(f"analysis:ctx:{analysis_id}")
    if ctx is None:
        raise AnalysisError(
            "Analysis session expired or not found. Please re-run the route analysis.",
            status_code=404,
        )

    base_dep_utc: datetime = ctx["departure_utc"]
    load_weight_lb: float = float(ctx["load_weight_lb"])
    interval_miles: int = int(ctx["interval_miles"])
    gust_aware: bool = bool(ctx["gust_aware"])
    demo_scenario: str | None = ctx["demo_scenario"]
    raw_routes: list[RawRouteCandidate] = ctx["raw_routes"]
    origin_info: dict[str, object] = ctx["origin"]
    dest_info: dict[str, object] = ctx["destination"]

    all_coords: list[tuple[float, float]] = []
    for r in raw_routes:
        all_coords.extend(r.coordinates)

    grid_map, _, _ = fetch_grid_forecasts(
        all_coords,
        base_dep_utc,
        demo_scenario=demo_scenario,
    )

    origin_lat = float(origin_info["lat"])  # type: ignore[arg-type]
    origin_lng = float(origin_info["lng"])  # type: ignore[arg-type]
    origin_label = str(origin_info["label"])
    dest_label = str(dest_info["label"])

    # Scan offsets from -3h to +12h in 1h steps
    offsets = list(range(-3, 13))
    window_options: list[dict[str, object]] = []

    best_option: dict[str, object] | None = None
    best_sort_tuple: tuple[int, float, float, float, int] | None = None
    baseline_option: dict[str, object] | None = None

    for offset_h in offsets:
        cand_dep_utc = base_dep_utc + timedelta(hours=offset_h)
        scored_list: list[ScoredRoute] = []
        for r_cand in raw_routes:
            s_route, _ = _evaluate_route_for_departure(
                raw_route=r_cand,
                departure_utc=cand_dep_utc,
                interval_miles=interval_miles,
                load_weight_lb=load_weight_lb,
                gust_aware=gust_aware,
                grid_map=grid_map,
                origin_label=origin_label,
                dest_label=dest_label,
            )
            scored_list.append(s_route)

        ranked, rec = rank_and_recommend_routes(scored_list)
        top = ranked[0]
        _, local_disp, _, _ = format_local_eta(cand_dep_utc, origin_lat, origin_lng)

        entry: dict[str, object] = {
            "offsetHours": offset_h,
            "departureTimeUtc": cand_dep_utc.isoformat(),
            "departureTimeLocal": local_disp,
            "allBlocked": rec.all_blocked,
            "bestRouteId": top.id,
            "bestRouteLabel": top.label,
            "noTravelMiles": top.metrics.no_travel_miles,
            "severeMiles": top.metrics.severe_miles,
            "highMiles": top.metrics.high_miles,
            "avgRisk": top.metrics.avg_risk,
            "durationMin": top.duration_min,
        }
        window_options.append(entry)

        if offset_h == 0:
            baseline_option = entry

        sort_tuple = (
            1 if rec.all_blocked else 0,
            round(top.metrics.no_travel_miles, 1),
            round(top.metrics.severe_miles, 1),
            round(top.metrics.high_miles, 1),
            round(top.metrics.avg_risk, 2),
            abs(offset_h),
        )
        if best_sort_tuple is None or sort_tuple < best_sort_tuple:  # type: ignore[operator]
            best_sort_tuple = sort_tuple  # type: ignore[assignment]
            best_option = entry

    suggestion_text = "Your selected departure time is already optimal within the ±12h window."
    if best_option is not None and baseline_option is not None:
        best_offset = int(best_option["offsetHours"])  # type: ignore[arg-type]
        if best_offset != 0:
            dir_str = f"{best_offset:+d} hours"
            if bool(baseline_option["allBlocked"]) and not bool(best_option["allBlocked"]):
                suggestion_text = (
                    f"Departing {dir_str} ({best_option['departureTimeLocal']}) clears all No Travel blocks "
                    f"on {best_option['bestRouteLabel']}."
                )
            else:
                sev_diff = float(baseline_option["severeMiles"]) - float(best_option["severeMiles"])  # type: ignore[arg-type]
                risk_diff = float(baseline_option["avgRisk"]) - float(best_option["avgRisk"])  # type: ignore[arg-type]
                if sev_diff > 0.5 or risk_diff > 0.05:
                    suggestion_text = (
                        f"Departing {dir_str} ({best_option['departureTimeLocal']}) reduces Severe miles by "
                        f"{max(0.0, sev_diff):.0f} mi and lowers average risk to {best_option['avgRisk']:.2f}."
                    )

    result = {
        "analysisId": analysis_id,
        "recommendedOffsetHours": best_option["offsetHours"] if best_option else 0,
        "recommendedDepartureLocal": best_option["departureTimeLocal"] if best_option else "",
        "suggestion": suggestion_text,
        "windows": window_options,
    }
    cache.set(scan_cache_key, result, timeout=ANALYSIS_CACHE_TTL_SECONDS)
    return result
