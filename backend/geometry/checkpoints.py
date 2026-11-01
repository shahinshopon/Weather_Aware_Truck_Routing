"""Pure geometry, checkpoint spacing, ETA interpolation, and corridor grid functions (CP-1 to CP-5, HM-1, HM-2)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

try:
    from timezonefinder import TimezoneFinder

    _TZ_FINDER: TimezoneFinder | None = TimezoneFinder(in_memory=True)
except Exception:  # pragma: no cover
    _TZ_FINDER = None

EARTH_RADIUS_MILES: float = 3958.7613


@dataclass(frozen=True)
class RouteSection:
    """Per-section distance and duration along a route geometry."""

    start_mile: float
    end_mile: float
    duration_seconds: float


@dataclass(frozen=True)
class CheckpointGeometry:
    """Geometric and temporal properties of a checkpoint along a route."""

    index: int
    mile: float
    lat: float
    lng: float
    segment_miles: float
    eta_utc: datetime
    eta_local_iso: str
    eta_local_display: str
    timezone_name: str
    timezone_abbr: str
    eta_is_estimate: bool = False


@dataclass(frozen=True)
class CorridorCell:
    """Grid cell in the 0-48h weather heatmap corridor."""

    cell_id: str
    lat: float
    lng: float
    grid_lat: float
    grid_lng: float
    route_ids: tuple[str, ...]
    offset_miles: float


def haversine_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in miles between two (lat, lng) points."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)

    a = (
        math.sin(d_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))
    return EARTH_RADIUS_MILES * c


def encode_polyline(coordinates: list[tuple[float, float]], precision: int = 5) -> str:
    """Encode a list of (lat, lng) pairs into an encoded polyline string."""
    factor = 10**precision
    output: list[str] = []
    prev_lat = 0
    prev_lng = 0

    for lat, lng in coordinates:
        ilat = int(round(lat * factor))
        ilng = int(round(lng * factor))
        _encode_value(ilat - prev_lat, output)
        _encode_value(ilng - prev_lng, output)
        prev_lat = ilat
        prev_lng = ilng

    return "".join(output)


def _encode_value(value: int, output: list[str]) -> None:
    value = ~(value << 1) if value < 0 else (value << 1)
    while value >= 0x20:
        output.append(chr((0x20 | (value & 0x1F)) + 63))
        value >>= 5
    output.append(chr(value + 63))


def decode_polyline(encoded: str, precision: int = 5) -> list[tuple[float, float]]:
    """Decode an encoded polyline string into a list of (lat, lng) pairs."""
    factor = float(10**precision)
    coordinates: list[tuple[float, float]] = []
    index = 0
    lat = 0
    lng = 0
    length = len(encoded)

    while index < length:
        result = 0
        shift = 0
        while True:
            b = ord(encoded[index]) - 63
            index += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        dlat = ~(result >> 1) if (result & 1) else (result >> 1)
        lat += dlat

        result = 0
        shift = 0
        while True:
            b = ord(encoded[index]) - 63
            index += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        dlng = ~(result >> 1) if (result & 1) else (result >> 1)
        lng += dlng

        coordinates.append((lat / factor, lng / factor))

    return coordinates


def get_timezone_name(lat: float, lng: float) -> str:
    """
    Resolve IANA timezone name for a (lat, lng) coordinate (CP-5).
    Uses TimezoneFinder when available and falls back to longitudinal US timezone bands.
    """
    if _TZ_FINDER is not None:
        tz_name = _TZ_FINDER.timezone_at(lat=lat, lng=lng)
        if tz_name:
            return tz_name

    # Deterministic fallback across North American longitudes
    if lng >= -85.0:
        return "America/New_York"
    if lng >= -102.0:
        return "America/Chicago"
    if lng >= -115.0:
        return "America/Denver"
    return "America/Los_Angeles"


def format_local_eta(eta_utc: datetime, lat: float, lng: float) -> tuple[str, str, str, str]:
    """
    Convert a UTC datetime to the checkpoint's local timezone (CP-5).
    Returns (local_iso, local_display, timezone_name, timezone_abbr).
    Correct across timezone lines and DST transitions.
    """
    if eta_utc.tzinfo is None:
        eta_utc = eta_utc.replace(tzinfo=UTC)
    else:
        eta_utc = eta_utc.astimezone(UTC)

    tz_name = get_timezone_name(lat, lng)
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("UTC")
        tz_name = "UTC"

    local_dt = eta_utc.astimezone(tz)
    tz_abbr = local_dt.strftime("%Z") or "UTC"
    local_iso = local_dt.isoformat()
    local_display = f"{local_dt.strftime('%b %d, %I:%M %p')} {tz_abbr}"
    return local_iso, local_display, tz_name, tz_abbr


def compute_cumulative_miles(coords: list[tuple[float, float]]) -> list[float]:
    """Compute cumulative distance in miles along a list of (lat, lng) vertices."""
    if not coords:
        return []
    cum = [0.0]
    for i in range(1, len(coords)):
        seg = haversine_miles(
            coords[i - 1][0], coords[i - 1][1], coords[i][0], coords[i][1]
        )
        cum.append(cum[-1] + seg)
    return cum


def interpolate_point_at_mile(
    coords: list[tuple[float, float]],
    cum_miles: list[float],
    target_mile: float,
) -> tuple[float, float]:
    """Interpolate (lat, lng) at a target cumulative distance along the route."""
    if not coords:
        raise ValueError("Route coordinates cannot be empty")
    if len(coords) == 1 or target_mile <= 0.0:
        return coords[0]
    total = cum_miles[-1]
    if target_mile >= total or total <= 0.0:
        return coords[-1]

    # Binary search or linear scan for bracketing vertices
    lo = 0
    hi = len(cum_miles) - 1
    while lo < hi - 1:
        mid = (lo + hi) // 2
        if cum_miles[mid] <= target_mile:
            lo = mid
        else:
            hi = mid

    d0 = cum_miles[lo]
    d1 = cum_miles[hi]
    span = d1 - d0
    if span <= 1e-9:
        return coords[lo]
    ratio = (target_mile - d0) / span
    lat = coords[lo][0] + ratio * (coords[hi][0] - coords[lo][0])
    lng = coords[lo][1] + ratio * (coords[hi][1] - coords[lo][1])
    return (round(lat, 6), round(lng, 6))


def assign_segment_miles(checkpoint_miles: list[float], total_miles: float) -> list[float]:
    """
    CP-4 Segment attribution:
    Each checkpoint owns the stretch from the midpoint to the previous checkpoint
    to the midpoint to the next, so miles per risk level sum exactly to the route distance.
    """
    n = len(checkpoint_miles)
    if n == 0:
        return []
    if n == 1:
        return [round(total_miles, 4)]

    segments: list[float] = []
    for i in range(n):
        left = 0.0 if i == 0 else 0.5 * (checkpoint_miles[i - 1] + checkpoint_miles[i])
        right = (
            total_miles
            if i == n - 1
            else 0.5 * (checkpoint_miles[i] + checkpoint_miles[i + 1])
        )
        segments.append(max(0.0, right - left))

    return segments


def interpolate_elapsed_seconds(
    target_mile: float,
    total_miles: float,
    total_duration_seconds: float,
    sections: list[RouteSection] | None = None,
) -> tuple[float, bool]:
    """
    CP-2: Interpolate elapsed travel time in seconds at target_mile from per-section durations.
    Returns (elapsed_seconds, is_estimate).
    """
    if target_mile <= 0.0 or total_miles <= 0.0 or total_duration_seconds <= 0.0:
        return 0.0, not bool(sections)
    if target_mile >= total_miles:
        return float(total_duration_seconds), not bool(sections)

    if not sections:
        ratio = target_mile / total_miles
        return ratio * total_duration_seconds, True

    elapsed = 0.0
    for sec in sections:
        if target_mile >= sec.end_mile:
            elapsed += sec.duration_seconds
        elif target_mile > sec.start_mile:
            span = sec.end_mile - sec.start_mile
            if span > 1e-9:
                elapsed += ((target_mile - sec.start_mile) / span) * sec.duration_seconds
            break
        else:
            break

    return min(float(total_duration_seconds), max(0.0, elapsed)), False


def generate_checkpoints(
    coords: list[tuple[float, float]],
    departure_utc: datetime,
    interval_miles: float,
    total_duration_seconds: float,
    sections: list[RouteSection] | None = None,
    override_total_miles: float | None = None,
) -> list[CheckpointGeometry]:
    """
    CP-1 to CP-5:
    Walk route geometry with cumulative distance and place a checkpoint every N miles
    starting at mile 0. Origin and destination are always checkpoints, so a trip
    shorter than N miles still has two.
    """
    if not coords:
        raise ValueError("Route coordinates cannot be empty")
    if interval_miles <= 0:
        raise ValueError("interval_miles must be greater than 0")

    if departure_utc.tzinfo is None:
        departure_utc = departure_utc.replace(tzinfo=UTC)
    else:
        departure_utc = departure_utc.astimezone(UTC)

    raw_cum_miles = compute_cumulative_miles(coords)
    raw_total = raw_cum_miles[-1] if raw_cum_miles else 0.0
    total_miles = override_total_miles if (override_total_miles is not None and override_total_miles > 0) else raw_total

    # Scale cumulative miles if provider reported distance differs slightly from chord sum
    if raw_total > 1e-6 and total_miles > 0:
        scale = total_miles / raw_total
        cum_miles = [m * scale for m in raw_cum_miles]
    else:
        cum_miles = raw_cum_miles

    # Build target mile positions: 0, N, 2N, ..., and always destination
    mile_positions: list[float] = [0.0]
    current = float(interval_miles)
    while current < total_miles - 1e-3:
        mile_positions.append(round(current, 4))
        current += float(interval_miles)

    # Always include destination as final checkpoint (even if total_miles == 0 or < N)
    if len(mile_positions) == 1 or abs(mile_positions[-1] - total_miles) > 1e-3:
        mile_positions.append(round(total_miles, 4))

    segment_miles_list = assign_segment_miles(mile_positions, total_miles)

    checkpoints: list[CheckpointGeometry] = []
    prev_eta = departure_utc

    for idx, (mile_pos, seg_miles) in enumerate(
        zip(mile_positions, segment_miles_list, strict=True)
    ):
        if idx == 0:
            lat, lng = coords[0]
            elapsed_sec, is_est = 0.0, not bool(sections)
        elif idx == len(mile_positions) - 1:
            lat, lng = coords[-1]
            elapsed_sec, is_est = float(total_duration_seconds), not bool(sections)
        else:
            lat, lng = interpolate_point_at_mile(coords, cum_miles, mile_pos)
            elapsed_sec, is_est = interpolate_elapsed_seconds(
                mile_pos, total_miles, total_duration_seconds, sections
            )

        eta_utc = departure_utc + timedelta(seconds=elapsed_sec)
        # Guarantee monotonic ETAs along route
        if eta_utc < prev_eta:
            eta_utc = prev_eta
        prev_eta = eta_utc

        local_iso, local_display, tz_name, tz_abbr = format_local_eta(eta_utc, lat, lng)

        checkpoints.append(
            CheckpointGeometry(
                index=idx,
                mile=round(mile_pos, 2),
                lat=round(lat, 5),
                lng=round(lng, 5),
                segment_miles=round(seg_miles, 4),
                eta_utc=eta_utc,
                eta_local_iso=local_iso,
                eta_local_display=local_display,
                timezone_name=tz_name,
                timezone_abbr=tz_abbr,
                eta_is_estimate=is_est,
            )
        )

    return checkpoints


def point_at_elapsed_minutes(
    coords: list[tuple[float, float]],
    total_duration_minutes: float,
    elapsed_minutes: float,
) -> tuple[float, float, float]:
    """
    HM-8: Compute the truck's (lat, lng, mile) position along a route at a given elapsed time.
    """
    if not coords:
        return (0.0, 0.0, 0.0)
    cum_miles = compute_cumulative_miles(coords)
    total_miles = cum_miles[-1] if cum_miles else 0.0
    if elapsed_minutes <= 0.0 or total_duration_minutes <= 0.0:
        return (coords[0][0], coords[0][1], 0.0)
    if elapsed_minutes >= total_duration_minutes:
        return (coords[-1][0], coords[-1][1], round(total_miles, 1))

    ratio = elapsed_minutes / total_duration_minutes
    target_mile = ratio * total_miles
    lat, lng = interpolate_point_at_mile(coords, cum_miles, target_mile)
    return (lat, lng, round(target_mile, 1))


def route_overlap_ratio(
    coords_a: list[tuple[float, float]],
    coords_b: list[tuple[float, float]],
    sample_step_miles: float = 10.0,
    proximity_threshold_miles: float = 4.0,
) -> float:
    """
    RT-2: Compute fraction (0.0 to 1.0) of route A's interior length that lies within
    proximity_threshold_miles of route B. Used to drop routes overlapping by > 90%.
    """
    if not coords_a or not coords_b:
        return 0.0

    cum_a = compute_cumulative_miles(coords_a)
    cum_b = compute_cumulative_miles(coords_b)
    total_a = cum_a[-1]
    total_b = cum_b[-1]

    if total_a <= 1e-3 or total_b <= 1e-3:
        return 1.0

    num_samples = max(5, min(60, int(total_a / max(1.0, sample_step_miles))))
    samples_a = [
        interpolate_point_at_mile(coords_a, cum_a, (i / num_samples) * total_a)
        for i in range(1, num_samples)
    ]
    num_samples_b = max(10, min(80, int(total_b / max(1.0, sample_step_miles / 1.5))))
    samples_b = [
        interpolate_point_at_mile(coords_b, cum_b, (j / num_samples_b) * total_b)
        for j in range(num_samples_b + 1)
    ]

    if not samples_a:
        return 0.0

    overlapping = 0
    for lat_a, lng_a in samples_a:
        min_dist = min(
            haversine_miles(lat_a, lng_a, lat_b, lng_b) for lat_b, lng_b in samples_b
        )
        if min_dist <= proximity_threshold_miles:
            overlapping += 1

    return overlapping / len(samples_a)


def snap_to_grid(lat: float, lng: float, resolution_deg: float = 0.1) -> tuple[float, float]:
    """WX-2: Snap (lat, lng) coordinates to the forecast grid (~0.1 degree)."""
    grid_lat = round(round(lat / resolution_deg) * resolution_deg, 2)
    grid_lng = round(round(lng / resolution_deg) * resolution_deg, 2)
    return (grid_lat, grid_lng)


def _offset_lat_lng(
    lat: float,
    lng: float,
    bearing_rad: float,
    offset_miles: float,
) -> tuple[float, float]:
    """Offset a (lat, lng) point perpendicular to bearing_rad by offset_miles."""
    if abs(offset_miles) < 1e-6:
        return (lat, lng)
    perp_bearing = bearing_rad + (math.pi / 2.0)
    d_north_miles = offset_miles * math.cos(perp_bearing)
    d_east_miles = offset_miles * math.sin(perp_bearing)

    d_lat = d_north_miles / 69.0
    cos_lat = max(0.2, math.cos(math.radians(lat)))
    d_lng = d_east_miles / (69.172 * cos_lat)
    return (round(lat + d_lat, 4), round(lng + d_lng, 4))


def build_corridor_grid(
    routes: list[tuple[str, list[tuple[float, float]]]],
    step_miles: float = 10.0,
    lateral_offsets_miles: tuple[float, ...] = (0.0, -14.0, 14.0, -25.0, 25.0),
    max_cells: int = 1500,
    grid_resolution_deg: float = 0.1,
) -> list[CorridorCell]:
    """
    HM-1, HM-2: Build the union corridor grid across all routes buffered by ~25 miles each side.
    Samples along each route about every 10 miles with lateral offsets, de-duplicated on the
    forecast grid, and capped at max_cells (~1,500).
    """
    cell_map: dict[tuple[float, float], CorridorCell] = {}

    # Adapt step_miles if corridor is very long so we stay well within max_cells
    total_corridor_miles = 0.0
    route_cum_data: list[tuple[str, list[tuple[float, float]], list[float], float]] = []
    for route_id, coords in routes:
        if not coords:
            continue
        cum = compute_cumulative_miles(coords)
        dist = cum[-1] if cum else 0.0
        total_corridor_miles += dist
        route_cum_data.append((route_id, coords, cum, dist))

    effective_step = max(step_miles, total_corridor_miles / max(50.0, max_cells / max(1, len(lateral_offsets_miles))))

    # Pass 1: centerline cells (offset 0) first so route centerlines are always prioritized
    # Pass 2: lateral buffer offsets (-14, +14, -25, +25 miles)
    for offset in lateral_offsets_miles:
        for route_id, coords, cum_miles, total_miles in route_cum_data:
            num_steps = max(2, int(total_miles / max(1.0, effective_step)) + 1)
            for step_idx in range(num_steps + 1):
                if len(cell_map) >= max_cells:
                    break
                mile = min(total_miles, step_idx * effective_step)
                lat, lng = interpolate_point_at_mile(coords, cum_miles, mile)

                # Estimate local bearing for perpendicular lateral buffer
                next_mile = min(total_miles, mile + 5.0)
                prev_mile = max(0.0, mile - 5.0)
                p1 = interpolate_point_at_mile(coords, cum_miles, prev_mile)
                p2 = interpolate_point_at_mile(coords, cum_miles, next_mile)
                bearing = math.atan2(p2[1] - p1[1], p2[0] - p1[0])

                olat, olng = _offset_lat_lng(lat, lng, bearing, offset)
                glat, glng = snap_to_grid(olat, olng, grid_resolution_deg)
                key = (glat, glng)

                if key in cell_map:
                    existing = cell_map[key]
                    if route_id not in existing.route_ids:
                        cell_map[key] = CorridorCell(
                            cell_id=existing.cell_id,
                            lat=existing.lat,
                            lng=existing.lng,
                            grid_lat=glat,
                            grid_lng=glng,
                            route_ids=(*existing.route_ids, route_id),
                            offset_miles=min(abs(existing.offset_miles), abs(offset)),
                        )
                else:
                    cell_id = f"{glat:.2f},{glng:.2f}"
                    cell_map[key] = CorridorCell(
                        cell_id=cell_id,
                        lat=glat,
                        lng=glng,
                        grid_lat=glat,
                        grid_lng=glng,
                        route_ids=(route_id,),
                        offset_miles=offset,
                    )

    return list(cell_map.values())[:max_cells]
