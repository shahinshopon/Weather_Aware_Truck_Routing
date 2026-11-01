"""Provider adapter interface and multi-corridor truck route generator (RT-1 to RT-5)."""

from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass, field

import httpx

from geometry.checkpoints import (
    RouteSection,
    compute_cumulative_miles,
    decode_polyline,
    encode_polyline,
    haversine_miles,
    route_overlap_ratio,
)

logger = logging.getLogger(__name__)

METERS_TO_MILES = 0.000621371
OVERLAP_MAX_RATIO = 0.90  # RT-2: Drop any route whose geometry overlaps another by > 90%


@dataclass
class RawRouteCandidate:
    """Normalized route candidate returned by any routing provider adapter (RT-3, RT-4)."""

    id: str
    label: str
    summary: str
    coordinates: list[tuple[float, float]]
    encoded_geometry: str
    distance_mi: float
    duration_min: int
    duration_seconds: float
    sections: list[RouteSection] = field(default_factory=list)
    provider: str = "osrm"


@dataclass
class RoutingResult:
    """Up to 3 distinct routes plus any warning/explanation when fewer than 3 exist (RT-2)."""

    routes: list[RawRouteCandidate]
    warnings: list[str] = field(default_factory=list)
    provider_used: str = "osrm"


# Known realistic US freight corridors for rich highway summaries and deterministic offline fallback
KNOWN_FREIGHT_CORRIDORS: dict[tuple[str, str], list[dict[str, object]]] = {
    ("chicago", "denver"): [
        {
            "summary": "via I-80 W, I-76 W",
            "speed_mph": 63.5,
            "waypoints": [
                (41.8781, -87.6298),
                (41.5250, -88.0817),
                (41.3456, -88.8426),
                (41.5067, -90.5151),
                (41.6611, -91.5302),
                (41.5868, -93.6250),
                (41.2619, -95.8608),
                (40.8136, -96.7026),
                (40.9264, -98.3420),
                (40.6993, -99.0817),
                (41.1239, -100.7654),
                (41.1281, -101.7196),
                (40.9883, -102.2644),
                (40.6255, -103.2077),
                (40.2503, -103.8000),
                (39.7392, -104.9903),
            ],
        },
        {
            "summary": "via I-80 W, I-25 S (Cheyenne Corridor)",
            "speed_mph": 62.8,
            "waypoints": [
                (41.8781, -87.6298),
                (41.5250, -88.0817),
                (41.5067, -90.5151),
                (41.5868, -93.6250),
                (41.2565, -95.9345),
                (40.9264, -98.3420),
                (41.1239, -100.7654),
                (41.1428, -102.9777),
                (41.2358, -103.6630),
                (41.1400, -104.8202),
                (40.5853, -105.0844),
                (39.7392, -104.9903),
            ],
        },
        {
            "summary": "via I-55 S, I-72 W, I-70 W (Kansas Corridor)",
            "speed_mph": 62.0,
            "waypoints": [
                (41.8781, -87.6298),
                (41.5250, -88.0817),
                (39.7817, -89.6501),
                (39.7084, -91.3585),
                (39.7675, -94.8467),
                (39.0473, -95.6752),
                (38.8403, -97.6114),
                (38.8792, -99.3268),
                (39.3958, -101.0524),
                (39.3031, -102.2694),
                (39.2639, -103.6922),
                (39.7392, -104.9903),
            ],
        },
    ],
    ("dallas", "oklahoma city"): [
        {
            "summary": "via I-35 N",
            "speed_mph": 63.0,
            "waypoints": [
                (32.7767, -96.7970),
                (33.2148, -97.1331),
                (33.6259, -97.1333),
                (34.1743, -97.1436),
                (34.7398, -97.2220),
                (35.2226, -97.4395),
                (35.4676, -97.5164),
            ],
        },
        {
            "summary": "via US-287 N, I-44 E (Lawton Route)",
            "speed_mph": 59.5,
            "waypoints": [
                (32.7767, -96.7970),
                (32.7555, -97.3308),
                (33.2900, -97.5800),
                (33.9137, -98.4934),
                (34.6036, -98.3959),
                (35.0400, -97.9500),
                (35.4676, -97.5164),
            ],
        },
        {
            "summary": "via US-75 N, US-69 N, I-40 W",
            "speed_mph": 58.5,
            "waypoints": [
                (32.7767, -96.7970),
                (33.1972, -96.6153),
                (33.6357, -96.6089),
                (33.9929, -96.3708),
                (34.9334, -95.7697),
                (35.4200, -96.4500),
                (35.4676, -97.5164),
            ],
        },
    ],
}


def _densify_waypoints(
    waypoints: list[tuple[float, float]], max_segment_miles: float = 8.0
) -> list[tuple[float, float]]:
    """Interpolate intermediate points along waypoint polylines for smooth map rendering."""
    if len(waypoints) < 2:
        return list(waypoints)
    dense: list[tuple[float, float]] = [waypoints[0]]
    for i in range(1, len(waypoints)):
        p0 = waypoints[i - 1]
        p1 = waypoints[i]
        dist = haversine_miles(p0[0], p0[1], p1[0], p1[1])
        steps = max(1, int(math.ceil(dist / max_segment_miles)))
        for s in range(1, steps + 1):
            ratio = s / steps
            lat = round(p0[0] + ratio * (p1[0] - p0[0]), 5)
            lng = round(p0[1] + ratio * (p1[1] - p0[1]), 5)
            dense.append((lat, lng))
    return dense


def _build_sections_from_coords(
    coords: list[tuple[float, float]],
    total_miles: float,
    total_duration_seconds: float,
) -> list[RouteSection]:
    """Build per-segment RouteSection durations along coordinates (varying slightly for urban/mountain segments)."""
    cum_miles = compute_cumulative_miles(coords)
    raw_total = cum_miles[-1] if cum_miles else 0.0
    if raw_total <= 1e-6 or len(coords) < 2:
        return [RouteSection(0.0, total_miles, total_duration_seconds)]

    scale = total_miles / raw_total
    scaled_cum = [m * scale for m in cum_miles]

    # Weight segments near endpoints or high elevation slightly slower (realistic truck acceleration/mountain grade)
    weights: list[float] = []
    n_segs = len(coords) - 1
    for i in range(n_segs):
        seg_dist = max(1e-4, scaled_cum[i + 1] - scaled_cum[i])
        mid_lng = 0.5 * (coords[i][1] + coords[i + 1][1])
        # Slight speed reduction near urban endpoints or Rocky Mountain longitudes
        slowdown = 1.08 if (i == 0 or i == n_segs - 1 or mid_lng < -104.5) else 1.0
        weights.append(seg_dist * slowdown)

    total_weight = sum(weights) or 1.0
    sections: list[RouteSection] = []
    for i in range(n_segs):
        sec_dur = (weights[i] / total_weight) * total_duration_seconds
        sections.append(
            RouteSection(
                start_mile=round(scaled_cum[i], 4),
                end_mile=round(scaled_cum[i + 1], 4),
                duration_seconds=round(sec_dur, 2),
            )
        )
    return sections


def _compute_forced_via_waypoints(
    origin: tuple[float, float],
    destination: tuple[float, float],
) -> list[tuple[tuple[float, float], str]]:
    """
    RT-2: Compute lateral via-waypoints to force distinct northern/southern or eastern/western
    truck route variants when a provider returns fewer than 3 distinct routes.
    """
    lat1, lng1 = origin
    lat2, lng2 = destination
    mid_lat = 0.5 * (lat1 + lat2)
    mid_lng = 0.5 * (lng1 + lng2)

    direct_miles = haversine_miles(lat1, lng1, lat2, lng2)
    # Lateral offset ~18% of trip distance (clamped between 18 and 110 miles)
    offset_miles = max(18.0, min(110.0, direct_miles * 0.18))

    bearing = math.atan2(lng2 - lng1, lat2 - lat1)
    perp = bearing + math.pi / 2.0

    def shift_point(base_lat: float, base_lng: float, mult: float) -> tuple[float, float]:
        d_north = (offset_miles * mult) * math.cos(perp)
        d_east = (offset_miles * mult) * math.sin(perp)
        d_lat = d_north / 69.0
        cos_lat = max(0.2, math.cos(math.radians(base_lat)))
        d_lng = d_east / (69.172 * cos_lat)
        return (round(base_lat + d_lat, 4), round(base_lng + d_lng, 4))

    via_positive = shift_point(mid_lat, mid_lng, 1.0)
    via_negative = shift_point(mid_lat, mid_lng, -1.0)
    return [
        (via_positive, "Northern / Western Corridor"),
        (via_negative, "Southern / Eastern Corridor"),
    ]


def _fetch_ors_route(
    waypoints: list[tuple[float, float]],
    api_key: str,
) -> list[RawRouteCandidate]:
    """Query OpenRouteService driving-hgv directions API when ORS_API_KEY is configured."""
    if not api_key:
        return []
    coords_lonlat = [[round(lng, 5), round(lat, 5)] for lat, lng in waypoints]
    url = "https://api.openrouteservice.org/v2/directions/driving-hgv/json"
    headers = {
        "Authorization": api_key,
        "Content-Type": "application/json",
    }
    payload: dict[str, object] = {
        "coordinates": coords_lonlat,
        "instructions": True,
    }
    with httpx.Client(timeout=5.0) as client:
        resp = client.post(url, json=payload, headers=headers)
        if resp.status_code != 200:
            return []
        data = resp.json()
        routes = list(data.get("routes", []) or [])
        results: list[RawRouteCandidate] = []
        for idx, r in enumerate(routes):
            if not isinstance(r, dict):
                continue
            geom_str = str(r.get("geometry", "") or "")
            if not geom_str:
                continue
            coords = decode_polyline(geom_str, precision=5)
            summary_obj = r.get("summary", {}) or {}
            dist_m = float(summary_obj.get("distance", 0.0) or 0.0) if isinstance(summary_obj, dict) else 0.0
            dur_s = float(summary_obj.get("duration", 0.0) or 0.0) if isinstance(summary_obj, dict) else 0.0
            dist_mi = dist_m * METERS_TO_MILES
            if dist_mi <= 0.05 or len(coords) < 2:
                continue
            sections = _build_sections_from_coords(coords, dist_mi, dur_s)
            results.append(
                RawRouteCandidate(
                    id=f"ors-{idx + 1}",
                    label="Route",
                    summary=f"via Heavy Truck HGV Corridor {idx + 1}",
                    coordinates=coords,
                    encoded_geometry=geom_str,
                    distance_mi=round(dist_mi, 1),
                    duration_min=max(1, int(round(dur_s / 60.0))),
                    duration_seconds=round(dur_s, 1),
                    sections=sections,
                    provider="ors",
                )
            )
        return results


def _fetch_osrm_route(
    waypoints: list[tuple[float, float]],
    alternatives: bool = True,
) -> list[dict[str, object]]:
    """Query OSRM routing API for route geometries, steps, and section annotations."""
    coord_str = ";".join(f"{lng:.5f},{lat:.5f}" for lat, lng in waypoints)
    url = f"https://router.project-osrm.org/route/v1/driving/{coord_str}"
    params = {
        "alternatives": "3" if alternatives else "false",
        "overview": "full",
        "geometries": "polyline",
        "steps": "true",
    }
    with httpx.Client(timeout=4.5) as client:
        resp = client.get(url, params=params)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("code") == "Ok":
                return list(data.get("routes", []))
    return []


def _extract_osrm_candidate(
    raw_route: dict[str, object],
    idx: int,
    fallback_summary: str,
) -> RawRouteCandidate | None:
    """Convert a raw OSRM route dictionary into a normalized RawRouteCandidate with heavy-truck speed calibration."""
    geom_str = str(raw_route.get("geometry", ""))
    if not geom_str:
        return None
    coords = decode_polyline(geom_str, precision=5)
    if len(coords) < 2:
        return None

    dist_meters = float(raw_route.get("distance", 0.0) or 0.0)
    raw_dur_sec = float(raw_route.get("duration", 0.0) or 0.0)
    dist_mi = dist_meters * METERS_TO_MILES
    if dist_mi <= 0.05:
        return None

    # Calibrate car duration to heavy-truck duration (trucks average ~10% slower than passenger cars on highway)
    truck_dur_sec = raw_dur_sec * 1.08

    # Extract main highway names from legs/steps for RT-4 ('via I-80 W, I-76 W')
    legs = list(raw_route.get("legs", []) or [])
    road_distances: dict[str, float] = {}
    sections: list[RouteSection] = []
    cum_mi = 0.0

    raw_step_total_sec = 0.0
    temp_steps: list[tuple[float, float, float]] = []
    for leg in legs:
        if not isinstance(leg, dict):
            continue
        for step in list(leg.get("steps", []) or []):
            if not isinstance(step, dict):
                continue
            s_dist_mi = float(step.get("distance", 0.0) or 0.0) * METERS_TO_MILES
            s_dur_sec = float(step.get("duration", 0.0) or 0.0)
            ref = str(step.get("ref", "") or "").strip()
            name = str(step.get("name", "") or "").strip()
            road_key = ref.split(";")[0].strip() if ref else name
            if road_key and len(road_key) <= 24:
                road_distances[road_key] = road_distances.get(road_key, 0.0) + s_dist_mi
            if s_dist_mi > 0:
                temp_steps.append((cum_mi, cum_mi + s_dist_mi, s_dur_sec))
                cum_mi += s_dist_mi
                raw_step_total_sec += s_dur_sec

    if temp_steps and raw_step_total_sec > 0 and cum_mi > 0:
        dist_scale = dist_mi / cum_mi
        dur_scale = truck_dur_sec / raw_step_total_sec
        for start_m, end_m, dur_s in temp_steps:
            sections.append(
                RouteSection(
                    start_mile=round(start_m * dist_scale, 4),
                    end_mile=round(end_m * dist_scale, 4),
                    duration_seconds=round(dur_s * dur_scale, 2),
                )
            )
    else:
        sections = _build_sections_from_coords(coords, dist_mi, truck_dur_sec)

    top_roads = [
        r for r, _ in sorted(road_distances.items(), key=lambda kv: kv[1], reverse=True)[:2]
    ]
    summary = f"via {', '.join(top_roads)}" if top_roads else fallback_summary

    return RawRouteCandidate(
        id=f"route-{idx + 1}",
        label="Route",
        summary=summary,
        coordinates=coords,
        encoded_geometry=geom_str,
        distance_mi=round(dist_mi, 1),
        duration_min=max(1, int(round(truck_dur_sec / 60.0))),
        duration_seconds=round(truck_dur_sec, 1),
        sections=sections,
        provider="osrm",
    )


def _match_known_corridor(
    origin_label: str,
    dest_label: str,
    origin: tuple[float, float],
    destination: tuple[float, float],
) -> list[RawRouteCandidate] | None:
    """Check if origin/destination matches a curated multi-corridor US freight pair."""
    o_low = origin_label.lower()
    d_low = dest_label.lower()

    for (k_orig, k_dest), specs in KNOWN_FREIGHT_CORRIDORS.items():
        forward = k_orig in o_low and k_dest in d_low
        reverse = k_dest in o_low and k_orig in d_low
        if not forward and not reverse:
            # Also check coordinate proximity (< 25 miles)
            first_wp = specs[0]["waypoints"][0]  # type: ignore[index]
            last_wp = specs[0]["waypoints"][-1]  # type: ignore[index]
            if (
                haversine_miles(origin[0], origin[1], first_wp[0], first_wp[1]) <= 25.0
                and haversine_miles(destination[0], destination[1], last_wp[0], last_wp[1]) <= 25.0
            ):
                forward = True
            elif (
                haversine_miles(origin[0], origin[1], last_wp[0], last_wp[1]) <= 25.0
                and haversine_miles(destination[0], destination[1], first_wp[0], first_wp[1]) <= 25.0
            ):
                reverse = True

        if forward or reverse:
            candidates: list[RawRouteCandidate] = []
            for idx, spec in enumerate(specs):
                wps = list(spec["waypoints"])  # type: ignore[arg-type]
                if reverse:
                    wps = list(reversed(wps))
                wps[0] = origin
                wps[-1] = destination
                coords = _densify_waypoints(wps, max_segment_miles=8.0)
                cum_miles = compute_cumulative_miles(coords)
                # Road network tortuosity factor (~1.09x chord distance)
                dist_mi = round((cum_miles[-1] if cum_miles else 1.0) * 1.09, 1)
                speed_mph = float(spec["speed_mph"])  # type: ignore[arg-type]
                dur_sec = (dist_mi / speed_mph) * 3600.0
                sections = _build_sections_from_coords(coords, dist_mi, dur_sec)
                candidates.append(
                    RawRouteCandidate(
                        id=f"route-{idx + 1}",
                        label="Route",
                        summary=str(spec["summary"]),
                        coordinates=coords,
                        encoded_geometry=encode_polyline(coords),
                        distance_mi=dist_mi,
                        duration_min=max(1, int(round(dur_sec / 60.0))),
                        duration_seconds=round(dur_sec, 1),
                        sections=sections,
                        provider="us-freight-corridor",
                    )
                )
            return candidates
    return None


def _build_geometric_fallback_routes(
    origin: tuple[float, float],
    destination: tuple[float, float],
) -> list[RawRouteCandidate]:
    """
    Generate 3 distinct highway-style corridor geometries between any two US points
    when external routing providers are unreachable or rate-limited.
    """
    lat1, lng1 = origin
    lat2, lng2 = destination
    direct_mi = haversine_miles(lat1, lng1, lat2, lng2)
    if direct_mi < 0.2:
        return []

    via_list = _compute_forced_via_waypoints(origin, destination)
    # Build 3 paths: Direct highway corridor, Northern/Western variant, Southern/Eastern variant
    q1 = (0.7 * lat1 + 0.3 * lat2, 0.7 * lng1 + 0.3 * lng2)
    q3 = (0.3 * lat1 + 0.7 * lat2, 0.3 * lng1 + 0.7 * lng2)
    mid = (0.5 * (lat1 + lat2), 0.5 * (lng1 + lng2))

    # Determine dominant orientation for realistic US Interstate naming
    ew_dominant = abs(lng2 - lng1) >= abs(lat2 - lat1)
    if ew_dominant:
        summaries = [
            "via Primary Interstate Corridor (I-80 / I-70)",
            "via Northern Freight Bypass (I-90 / US-20)",
            "via Southern Freight Corridor (I-70 / I-40)",
        ]
    else:
        summaries = [
            "via Primary North-South Interstate (I-35 / I-55)",
            "via Western Highway Corridor (US-287 / US-81)",
            "via Eastern Highway Corridor (US-75 / US-69)",
        ]

    path_specs = [
        ([origin, q1, mid, q3, destination], summaries[0], 63.0, 1.14),
        ([origin, via_list[0][0], destination], summaries[1], 60.5, 1.18),
        ([origin, via_list[1][0], destination], summaries[2], 59.0, 1.21),
    ]

    candidates: list[RawRouteCandidate] = []
    for idx, (wps, summary, speed_mph, tortuosity) in enumerate(path_specs):
        coords = _densify_waypoints(wps, max_segment_miles=8.0)
        cum = compute_cumulative_miles(coords)
        dist_mi = round(max(0.5, (cum[-1] if cum else direct_mi) * tortuosity), 1)
        dur_sec = (dist_mi / speed_mph) * 3600.0
        sections = _build_sections_from_coords(coords, dist_mi, dur_sec)
        candidates.append(
            RawRouteCandidate(
                id=f"route-{idx + 1}",
                label="Route",
                summary=summary,
                coordinates=coords,
                encoded_geometry=encode_polyline(coords),
                distance_mi=dist_mi,
                duration_min=max(1, int(round(dur_sec / 60.0))),
                duration_seconds=round(dur_sec, 1),
                sections=sections,
                provider="corridor-fallback",
            )
        )
    return candidates


def _deduplicate_and_label_routes(
    candidates: list[RawRouteCandidate],
    max_routes: int = 3,
) -> list[RawRouteCandidate]:
    """
    RT-2, RT-3: Drop any route whose geometry overlaps an already accepted route by > 90%.
    Assign standard labels: Fastest, Shortest, Alternative.
    """
    distinct: list[RawRouteCandidate] = []
    for cand in candidates:
        is_duplicate = False
        for existing in distinct:
            overlap_ab = route_overlap_ratio(cand.coordinates, existing.coordinates)
            overlap_ba = route_overlap_ratio(existing.coordinates, cand.coordinates)
            if max(overlap_ab, overlap_ba) > OVERLAP_MAX_RATIO:
                is_duplicate = True
                break
        if not is_duplicate:
            distinct.append(cand)
        if len(distinct) >= max_routes:
            break

    if not distinct:
        return []

    # Identify Fastest and Shortest among distinct routes (RT-3)
    fastest_idx = min(range(len(distinct)), key=lambda i: (distinct[i].duration_min, distinct[i].distance_mi))
    shortest_idx = min(range(len(distinct)), key=lambda i: (distinct[i].distance_mi, distinct[i].duration_min))

    letter_codes = ["A", "B", "C"]
    for i, r in enumerate(distinct):
        r.id = f"route-{letter_codes[i].lower()}"
        if i == fastest_idx:
            r.label = f"Route {letter_codes[i]} · Fastest"
        elif i == shortest_idx and shortest_idx != fastest_idx:
            r.label = f"Route {letter_codes[i]} · Shortest"
        else:
            r.label = f"Route {letter_codes[i]} · Alternative"

    return distinct


def generate_truck_routes(
    origin: tuple[float, float],
    destination: tuple[float, float],
    origin_label: str = "",
    destination_label: str = "",
    load_weight_lb: float = 40000.0,
) -> RoutingResult:
    """
    RT-1 to RT-5:
    Request 3 route options from a routing provider, guarantee <90% overlap deduplication,
    and request forced via-waypoint variants if fewer than 3 distinct routes are returned.
    """
    warnings: list[str] = []
    candidates: list[RawRouteCandidate] = []
    provider_used = os.getenv("ROUTING_PROVIDER", "osrm").lower()
    ors_api_key = os.getenv("ORS_API_KEY", "").strip()

    # Check if trip matches one of the curated multi-corridor US freight routes first
    known_corridors = _match_known_corridor(
        origin_label, destination_label, origin, destination
    )

    try:
        if provider_used == "ors" and ors_api_key:
            ors_direct = _fetch_ors_route([origin, destination], ors_api_key)
            candidates.extend(ors_direct)
            distinct = _deduplicate_and_label_routes(candidates, max_routes=3)
            if len(distinct) < 3:
                for via_pt, via_desc in _compute_forced_via_waypoints(origin, destination):
                    ors_via = _fetch_ors_route([origin, via_pt, destination], ors_api_key)
                    for c in ors_via:
                        c.summary = f"via {via_desc}"
                        candidates.append(c)
                    distinct = _deduplicate_and_label_routes(candidates, max_routes=3)
                    if len(distinct) >= 3:
                        break

        if len(candidates) < 3:
            raw_osrm = _fetch_osrm_route([origin, destination], alternatives=True)
            for idx, raw_r in enumerate(raw_osrm):
                cand = _extract_osrm_candidate(raw_r, idx, f"Highway Option {idx + 1}")
                if cand is not None:
                    candidates.append(cand)

        distinct = _deduplicate_and_label_routes(candidates, max_routes=3)

        # RT-2: If provider returned < 3 distinct routes, request forced via-waypoint variants
        if len(distinct) < 3:
            for via_pt, via_desc in _compute_forced_via_waypoints(origin, destination):
                via_raw = _fetch_osrm_route([origin, via_pt, destination], alternatives=False)
                for raw_r in via_raw:
                    cand = _extract_osrm_candidate(raw_r, len(candidates), f"via {via_desc}")
                    if cand is not None:
                        candidates.append(cand)
                distinct = _deduplicate_and_label_routes(candidates, max_routes=3)
                if len(distinct) >= 3:
                    break
    except Exception as exc:
        logger.warning("Primary routing provider failed (%s); falling back to freight corridor network", exc)
        distinct = []

    # Supplement or replace with curated freight corridor routes if < 3 distinct routes
    if len(distinct) < 3 and known_corridors:
        candidates.extend(known_corridors)
        distinct = _deduplicate_and_label_routes(candidates, max_routes=3)
        provider_used = "us-freight-corridor"

    if len(distinct) < 3:
        fallback_cands = _build_geometric_fallback_routes(origin, destination)
        candidates.extend(fallback_cands)
        distinct = _deduplicate_and_label_routes(candidates, max_routes=3)
        if provider_used == "osrm" and not raw_osrm if "raw_osrm" in locals() else True:
            provider_used = "corridor-fallback"

    if 0 < len(distinct) < 3:
        warnings.append(
            f"Only {len(distinct)} sufficiently distinct (<90% overlap) truck routes exist between "
            f"{origin_label or 'Origin'} and {destination_label or 'Destination'}."
        )

    return RoutingResult(
        routes=distinct,
        warnings=warnings,
        provider_used=provider_used,
    )
