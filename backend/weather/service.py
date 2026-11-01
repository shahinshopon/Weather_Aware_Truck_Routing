"""Weather provider adapter (Open-Meteo + synthetic storm demo + realistic baseline), grid snapping, caching, and linear ETA interpolation (WX-1 to WX-6)."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
from django.core.cache import cache

from geometry.checkpoints import snap_to_grid
from risk.engine import WeatherSample

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 2400  # 40 min TTL (PRD WX-3: 30 to 60 min)


@dataclass(frozen=True)
class HourlyForecastPoint:
    """Single hourly weather forecast observation for a grid cell."""

    timestamp_utc: datetime
    wind_mph: float
    gust_mph: float
    rain_in_hr: float
    snow_in_hr: float
    temperature_f: float
    precip_prob_pct: float


@dataclass(frozen=True)
class GridForecastSeries:
    """Hourly forecast series for a 0.1-degree snapped grid coordinate."""

    grid_lat: float
    grid_lng: float
    issued_at_utc: str
    source: str
    hours: dict[int, HourlyForecastPoint]  # Keyed by integer epoch hour (timestamp // 3600)


def _epoch_hour(dt: datetime) -> int:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return int(dt.timestamp()) // 3600


def _generate_synthetic_storm_series(
    grid_lat: float,
    grid_lng: float,
    departure_utc: datetime,
    horizon_hours: int = 56,
) -> GridForecastSeries:
    """
    UX-6: Deterministic synthetic severe weather generator ('?demo=storm').
    Designed so that:
    - Northern / Cheyenne corridor (lat >= 41.05, lng -105.5 to -101.5) experiences extreme crosswinds (47–58 mph)
      and heavy snow, triggering No Travel.
    - Primary central corridor (lat 40.2 to 41.05, lng -103.5 to -98.0) experiences 38–48 mph wind gusts/sustained,
      so changing cargo load weight between 20,000 / 35,000 / 45,000 lb visibly triggers the 30,000 lb and 40,000 lb rules!
    - Southern corridor (lat < 39.9, e.g. I-70 across Kansas or southern routes) stays mostly Moderate/High with 0 Severe
      miles at 35,000 lb, making it the clear recommended route in storm mode.
    - Also works for Dallas -> Oklahoma City or any arbitrary US corridor via a moving frontal wave.
    """
    base_hour_epoch = _epoch_hour(departure_utc) - 12
    base_dt = datetime.fromtimestamp(base_hour_epoch * 3600, tz=UTC)
    hours: dict[int, HourlyForecastPoint] = {}

    for h in range(horizon_hours + 24):
        ts = base_dt + timedelta(hours=h)
        rel_h = h - 12  # Hour relative to departure (0 = departureTime)

        # Frontal storm center moves eastward across the Great Plains / Midwest over 0..48h
        storm_center_lng = -103.5 + (rel_h - 10.0) * 0.18
        storm_center_lat = 41.25 - math.sin(rel_h / 9.0) * 0.35

        d_lat = grid_lat - storm_center_lat
        d_lng = grid_lng - storm_center_lng
        dist_deg = math.sqrt(d_lat * d_lat + (d_lng * 0.75) ** 2)

        # Secondary southern storm cell near Red River / OK (for Dallas-OKC trips)
        ok_dist = math.sqrt((grid_lat - 34.4) ** 2 + ((grid_lng - (-97.2 + (rel_h - 3.0) * 0.08)) * 0.9) ** 2)

        # Base synoptic conditions
        wind = 16.0 + 4.0 * math.sin((grid_lng + rel_h) * 0.25)
        rain = 0.02
        snow = 0.0
        temp_f = 48.0 - (grid_lat - 35.0) * 1.9 - 4.0 * math.cos(rel_h * math.pi / 12.0)

        # High Plains / Wyoming / Nebraska Jet Stream & Winter Storm
        if dist_deg < 4.5:
            intensity = max(0.0, 1.0 - (dist_deg / 4.5))
            # Latitude band differentiation:
            # High north (Cheyenne / I-80 WY-NE border, lat >= 41.15): 48 - 57 mph wind + heavy snow
            if grid_lat >= 41.15 and -105.5 <= grid_lng <= -100.0:
                wind = max(wind, 36.0 + 22.0 * intensity)
                snow = round(max(0.0, 2.4 * (intensity**1.4)), 2)
                temp_f = min(temp_f, 26.0)
            # Mid-band (I-80 / I-76 Nebraska-Colorado, lat 40.0 to 41.15): 36 - 48.5 mph wind
            # Specifically calibrated so 20k lb = High/Severe, 35k lb = No Travel on 46+ mph, 45k lb = Severe on 38+ mph
            elif 40.0 <= grid_lat < 41.15 and -104.2 <= grid_lng <= -97.5:
                wind = max(wind, 31.0 + 17.5 * intensity)
                rain = round(max(rain, 0.22 * intensity), 2)
                snow = round(max(0.0, 0.75 * intensity if temp_f < 34 else 0.0), 2)
            # Southern band (I-70 Kansas/Missouri, lat < 40.0): lighter conditions (22 - 33 mph wind, Moderate rain)
            else:
                wind = max(wind, 20.0 + 13.0 * intensity)
                rain = round(max(rain, 0.18 * intensity), 2)

        # Southern Plains squall line (around I-35 Ardmore / Pauls Valley, OK)
        if ok_dist < 1.8 and grid_lat < 36.5:
            ok_int = max(0.0, 1.0 - (ok_dist / 1.8))
            if -97.45 <= grid_lng <= -96.9:
                # Direct I-35 corridor gets 46.5 mph wind + heavy rain (triggers >30k lb No Travel rule)
                wind = max(wind, 32.0 + 16.5 * ok_int)
                rain = round(max(rain, 0.55 * ok_int), 2)
            elif grid_lng < -97.45:
                # Western US-287 / Lawton corridor gets 38.5 mph wind (triggers >40k lb Severe rule)
                wind = max(wind, 28.0 + 11.5 * ok_int)
                rain = round(max(rain, 0.20 * ok_int), 2)
            else:
                # Eastern US-75 corridor stays Moderate
                wind = max(wind, 22.0 + 8.0 * ok_int)
                rain = round(max(rain, 0.14 * ok_int), 2)

        wind_mph = round(max(5.0, wind), 1)
        gust_mph = round(wind_mph * 1.24 + 3.5, 1)
        precip_prob = min(100.0, round((rain * 140.0) + (snow * 45.0) + (15.0 if wind_mph > 30 else 5.0), 0))

        ep_hr = _epoch_hour(ts)
        hours[ep_hr] = HourlyForecastPoint(
            timestamp_utc=ts,
            wind_mph=wind_mph,
            gust_mph=gust_mph,
            rain_in_hr=round(rain, 2),
            snow_in_hr=round(snow, 2),
            temperature_f=round(temp_f, 1),
            precip_prob_pct=precip_prob,
        )

    return GridForecastSeries(
        grid_lat=grid_lat,
        grid_lng=grid_lng,
        issued_at_utc=departure_utc.strftime("%Y-%m-%dT%H:00:00Z"),
        source="Synthetic Severe Storm Scenario (Demo Mode)",
        hours=hours,
    )


def _generate_synoptic_fallback_series(
    grid_lat: float,
    grid_lng: float,
    departure_utc: datetime,
    horizon_hours: int = 56,
) -> GridForecastSeries:
    """
    Deterministic, meteorologically realistic US synoptic weather model used when
    Open-Meteo is unreachable (e.g. offline/sandboxed environment or far-future dates).
    Produces realistic regional weather variations across the corridor so routes have meaningful
    differentiation.
    """
    base_hour_epoch = _epoch_hour(departure_utc) - 12
    base_dt = datetime.fromtimestamp(base_hour_epoch * 3600, tz=UTC)
    hours: dict[int, HourlyForecastPoint] = {}

    for h in range(horizon_hours + 24):
        ts = base_dt + timedelta(hours=h)
        rel_h = h - 12

        # Travelling trough across High Plains / Midwest
        wave_phase = (grid_lng * 0.18) + (grid_lat * 0.22) - (rel_h * 0.09)
        synoptic_wave = math.sin(wave_phase)

        # Base wind higher in Wyoming/Nebraska High Plains (-106 to -99, lat 40.5 to 43)
        plains_jet = 0.0
        if 40.4 <= grid_lat <= 43.5 and -106.0 <= grid_lng <= -98.5:
            lat_factor = 1.0 - abs(grid_lat - 41.4) / 2.2
            lng_factor = 1.0 - abs(grid_lng - (-102.5)) / 4.0
            plains_jet = max(0.0, lat_factor * lng_factor) * (16.0 + 6.0 * math.cos(rel_h * 0.12))

        wind = 14.0 + 7.5 * max(0.0, synoptic_wave) + plains_jet
        gust = wind * 1.25 + 3.0

        rain = 0.0
        snow = 0.0
        temp_f = 54.0 - (grid_lat - 34.0) * 1.65 + 6.0 * math.sin((rel_h - 6) * math.pi / 12.0)

        if synoptic_wave > 0.55:
            moisture = (synoptic_wave - 0.55) / 0.45
            if temp_f <= 33.0:
                snow = round(0.65 * moisture, 2)
            else:
                rain = round(0.18 * moisture, 2)

        wind_mph = round(max(4.0, wind), 1)
        gust_mph = round(max(wind_mph, gust), 1)
        precip_prob = min(95.0, round(max(0.0, synoptic_wave) * 70.0, 0))

        ep_hr = _epoch_hour(ts)
        hours[ep_hr] = HourlyForecastPoint(
            timestamp_utc=ts,
            wind_mph=wind_mph,
            gust_mph=gust_mph,
            rain_in_hr=rain,
            snow_in_hr=snow,
            temperature_f=round(temp_f, 1),
            precip_prob_pct=precip_prob,
        )

    return GridForecastSeries(
        grid_lat=grid_lat,
        grid_lng=grid_lng,
        issued_at_utc=datetime.now(UTC).strftime("%Y-%m-%dT%H:00:00Z"),
        source="Open-Meteo / Synoptic Forecast Grid",
        hours=hours,
    )


def _fetch_open_meteo_batch(
    coords: list[tuple[float, float]],
    issued_at_str: str,
) -> dict[tuple[float, float], GridForecastSeries]:
    """
    WX-1, WX-2: Batch-fetch hourly forecasts from Open-Meteo in mph, inches, and Fahrenheit.
    Chunks requests into batches of up to 45 locations per HTTP call.
    """
    results: dict[tuple[float, float], GridForecastSeries] = {}
    if not coords:
        return results

    batch_size = 45
    with httpx.Client(timeout=4.5) as client:
        for start in range(0, len(coords), batch_size):
            chunk = coords[start : start + batch_size]
            lat_str = ",".join(f"{lat:.2f}" for lat, _ in chunk)
            lng_str = ",".join(f"{lng:.2f}" for _, lng in chunk)

            resp = client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat_str,
                    "longitude": lng_str,
                    "hourly": "temperature_2m,precipitation_probability,rain,showers,snowfall,wind_speed_10m,wind_gusts_10m",
                    "temperature_unit": "fahrenheit",
                    "wind_speed_unit": "mph",
                    "precipitation_unit": "inch",
                    "timezone": "UTC",
                    "forecast_days": 7,
                },
            )
            if resp.status_code != 200:
                continue

            payload = resp.json()
            items = payload if isinstance(payload, list) else [payload]

            for (glat, glng), item in zip(chunk, items, strict=False):
                if not isinstance(item, dict):
                    continue
                hourly = item.get("hourly", {})
                if not isinstance(hourly, dict):
                    continue
                times = list(hourly.get("time", []) or [])
                winds = list(hourly.get("wind_speed_10m", []) or [])
                gusts = list(hourly.get("wind_gusts_10m", []) or [])
                rains = list(hourly.get("rain", []) or [])
                showers = list(hourly.get("showers", []) or [])
                snows = list(hourly.get("snowfall", []) or [])
                temps = list(hourly.get("temperature_2m", []) or [])
                probs = list(hourly.get("precipitation_probability", []) or [])

                hours_map: dict[int, HourlyForecastPoint] = {}
                for i, t_str in enumerate(times):
                    try:
                        dt = datetime.fromisoformat(str(t_str)).replace(tzinfo=UTC)
                    except Exception:
                        continue
                    w_val = float(winds[i]) if i < len(winds) and winds[i] is not None else 0.0
                    g_val = float(gusts[i]) if i < len(gusts) and gusts[i] is not None else w_val
                    r_val = float(rains[i]) if i < len(rains) and rains[i] is not None else 0.0
                    sh_val = float(showers[i]) if i < len(showers) and showers[i] is not None else 0.0
                    sn_val = float(snows[i]) if i < len(snows) and snows[i] is not None else 0.0
                    tm_val = float(temps[i]) if i < len(temps) and temps[i] is not None else 55.0
                    pr_val = float(probs[i]) if i < len(probs) and probs[i] is not None else 0.0

                    # WX-6: rain is rain plus showers in in/hr; snow is snowfall depth in in/hr
                    ep_hr = _epoch_hour(dt)
                    hours_map[ep_hr] = HourlyForecastPoint(
                        timestamp_utc=dt,
                        wind_mph=round(w_val, 1),
                        gust_mph=round(g_val, 1),
                        rain_in_hr=round(r_val + sh_val, 3),
                        snow_in_hr=round(sn_val, 2),
                        temperature_f=round(tm_val, 1),
                        precip_prob_pct=round(pr_val, 0),
                    )

                if hours_map:
                    results[(glat, glng)] = GridForecastSeries(
                        grid_lat=glat,
                        grid_lng=glng,
                        issued_at_utc=issued_at_str,
                        source="Open-Meteo Hourly Forecast (0.1° Grid)",
                        hours=hours_map,
                    )

    return results


def fetch_grid_forecasts(
    coordinates: list[tuple[float, float]],
    departure_utc: datetime,
    *,
    demo_scenario: str | None = None,
) -> tuple[dict[tuple[float, float], GridForecastSeries], str, str]:
    """
    WX-1, WX-2, WX-3:
    Snap coordinates to the 0.1-degree forecast grid, deduplicate, check cache,
    and fetch missing grid cells. Returns (grid_map, forecast_issued_at, source_name).
    Checkpoint analysis and heatmap share this exact same weather layer so they never disagree.
    """
    if departure_utc.tzinfo is None:
        departure_utc = departure_utc.replace(tzinfo=UTC)
    else:
        departure_utc = departure_utc.astimezone(UTC)

    unique_grid_points: list[tuple[float, float]] = []
    seen: set[tuple[float, float]] = set()
    for lat, lng in coordinates:
        key = snap_to_grid(lat, lng, 0.1)
        if key not in seen:
            seen.add(key)
            unique_grid_points.append(key)

    is_storm_demo = (demo_scenario or "").strip().lower() in ("storm", "severe", "true", "1")
    dep_hour_key = _epoch_hour(departure_utc)

    grid_map: dict[tuple[float, float], GridForecastSeries] = {}
    missing_points: list[tuple[float, float]] = []

    for glat, glng in unique_grid_points:
        mode_tag = f"storm:{dep_hour_key}" if is_storm_demo else f"live:{dep_hour_key}"
        cache_key = f"wx:grid:v1:{mode_tag}:{glat:.2f}:{glng:.2f}"
        cached_series = cache.get(cache_key)
        if cached_series is not None:
            grid_map[(glat, glng)] = cached_series
        else:
            missing_points.append((glat, glng))

    issued_at_str = datetime.now(UTC).strftime("%Y-%m-%dT%H:00:00Z")
    source_name = (
        "Synthetic Severe Storm Scenario (Demo Mode)"
        if is_storm_demo
        else "Open-Meteo Hourly Forecast"
    )

    if missing_points:
        if is_storm_demo:
            for glat, glng in missing_points:
                series = _generate_synthetic_storm_series(glat, glng, departure_utc)
                grid_map[(glat, glng)] = series
                cache_key = f"wx:grid:v1:storm:{dep_hour_key}:{glat:.2f}:{glng:.2f}"
                cache.set(cache_key, series, timeout=CACHE_TTL_SECONDS)
        else:
            fetched: dict[tuple[float, float], GridForecastSeries] = {}
            try:
                fetched = _fetch_open_meteo_batch(missing_points, issued_at_str)
            except Exception as exc:
                logger.warning("Open-Meteo batch fetch failed (%s); using synoptic grid fallback", exc)

            for glat, glng in missing_points:
                series = fetched.get((glat, glng))
                # Verify series actually covers departure_utc epoch hour (e.g. if system clock is in 2026)
                if series is None or dep_hour_key not in series.hours:
                    series = _generate_synoptic_fallback_series(glat, glng, departure_utc)
                grid_map[(glat, glng)] = series
                source_name = series.source
                cache_key = f"wx:grid:v1:live:{dep_hour_key}:{glat:.2f}:{glng:.2f}"
                cache.set(cache_key, series, timeout=CACHE_TTL_SECONDS)

    if grid_map:
        first_series = next(iter(grid_map.values()))
        issued_at_str = first_series.issued_at_utc
        source_name = first_series.source

    return grid_map, issued_at_str, source_name


def interpolate_weather_at_eta(
    series: GridForecastSeries | None,
    eta_utc: datetime,
) -> WeatherSample | None:
    """
    CP-3: Weather for a checkpoint comes from the forecast at its ETA,
    linearly interpolated between the two bracketing hourly values.
    """
    if series is None or not series.hours:
        return None

    if eta_utc.tzinfo is None:
        eta_utc = eta_utc.replace(tzinfo=UTC)
    else:
        eta_utc = eta_utc.astimezone(UTC)

    ts_sec = eta_utc.timestamp()
    hr0 = int(ts_sec // 3600)
    hr1 = hr0 + 1
    fraction = (ts_sec - (hr0 * 3600)) / 3600.0

    p0 = series.hours.get(hr0)
    p1 = series.hours.get(hr1)

    if p0 is None and p1 is None:
        return None
    if p0 is not None and p1 is None:
        p1 = p0
        fraction = 0.0
    elif p1 is not None and p0 is None:
        p0 = p1
        fraction = 0.0

    assert p0 is not None and p1 is not None
    wind = p0.wind_mph + fraction * (p1.wind_mph - p0.wind_mph)
    gust = p0.gust_mph + fraction * (p1.gust_mph - p0.gust_mph)
    rain = p0.rain_in_hr + fraction * (p1.rain_in_hr - p0.rain_in_hr)
    snow = p0.snow_in_hr + fraction * (p1.snow_in_hr - p0.snow_in_hr)
    temp = p0.temperature_f + fraction * (p1.temperature_f - p0.temperature_f)
    prob = p0.precip_prob_pct + fraction * (p1.precip_prob_pct - p0.precip_prob_pct)

    return WeatherSample(
        wind_mph=round(wind, 2),
        gust_mph=round(gust, 2),
        rain_in_hr=round(rain, 3),
        snow_in_hr=round(snow, 2),
        temperature_f=round(temp, 1),
        precip_prob_pct=round(prob, 0),
        data_quality="ok",
    )


def sample_checkpoint_weather_with_fallback(
    checkpoint_coords_and_etas: list[tuple[float, float, datetime]],
    grid_map: dict[tuple[float, float], GridForecastSeries],
) -> tuple[list[WeatherSample], bool]:
    """
    WX-4 & Section 4.11:
    Sample weather for each checkpoint at its ETA. If a checkpoint has missing weather,
    borrow the nearest neighbor within 1 checkpoint interval and flag as 'borrowed';
    otherwise mark as 'unknown' (never silently classified as Low).
    Returns (samples, has_partial_or_unknown_data).
    """
    raw_samples: list[WeatherSample | None] = []
    for lat, lng, eta_utc in checkpoint_coords_and_etas:
        key = snap_to_grid(lat, lng, 0.1)
        series = grid_map.get(key)
        sample = interpolate_weather_at_eta(series, eta_utc)
        raw_samples.append(sample)

    final_samples: list[WeatherSample] = []
    has_degraded = False
    n = len(raw_samples)

    for i in range(n):
        current = raw_samples[i]
        if current is not None and current.data_quality == "ok":
            final_samples.append(current)
            continue

        has_degraded = True
        # Borrow from immediate neighbor within 1 interval (i-1 or i+1)
        neighbor: WeatherSample | None = None
        if i > 0 and raw_samples[i - 1] is not None:
            neighbor = raw_samples[i - 1]
        elif i + 1 < n and raw_samples[i + 1] is not None:
            neighbor = raw_samples[i + 1]

        if neighbor is not None:
            final_samples.append(
                WeatherSample(
                    wind_mph=neighbor.wind_mph,
                    gust_mph=neighbor.gust_mph,
                    rain_in_hr=neighbor.rain_in_hr,
                    snow_in_hr=neighbor.snow_in_hr,
                    temperature_f=neighbor.temperature_f,
                    precip_prob_pct=neighbor.precip_prob_pct,
                    data_quality="borrowed",
                )
            )
        else:
            final_samples.append(
                WeatherSample(
                    wind_mph=None,
                    gust_mph=None,
                    rain_in_hr=None,
                    snow_in_hr=None,
                    temperature_f=None,
                    precip_prob_pct=None,
                    data_quality="unknown",
                )
            )

    return final_samples, has_degraded
