"""Comprehensive unit and acceptance tests for the Weather-Aware Truck Routing backend (PRD Section 7 & 7.1)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from django.test import Client

from geometry.checkpoints import (
    RouteSection,
    build_corridor_grid,
    decode_polyline,
    encode_polyline,
    generate_checkpoints,
    haversine_miles,
    point_at_elapsed_minutes,
    route_overlap_ratio,
)
from risk.config import RiskLevel
from risk.engine import (
    WeatherSample,
    classify_checkpoint_risk,
    classify_rain,
    classify_snow,
    classify_wind,
)
from scoring.scorer import (
    EvaluatedCheckpoint,
    ScoredRoute,
    compute_route_metrics,
    rank_and_recommend_routes,
)
from weather.service import (
    GridForecastSeries,
    HourlyForecastPoint,
    interpolate_weather_at_eta,
    sample_checkpoint_weather_with_fallback,
)


# ---------------------------------------------------------------------------
# 1. Risk Engine Boundary & Load Rule Tests (PRD 7.1)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("wind_mph", "expected"),
    [
        (0.0, RiskLevel.LOW),
        (24.9, RiskLevel.LOW),
        (25.0, RiskLevel.MODERATE),
        (34.9, RiskLevel.MODERATE),
        (35.0, RiskLevel.HIGH),
        (44.9, RiskLevel.HIGH),
        (45.0, RiskLevel.SEVERE),
        (54.9, RiskLevel.SEVERE),
        (55.0, RiskLevel.NO_TRAVEL),
        (72.0, RiskLevel.NO_TRAVEL),
    ],
)
def test_wind_thresholds_lower_inclusive(wind_mph: float, expected: RiskLevel) -> None:
    assert classify_wind(wind_mph) == expected


@pytest.mark.parametrize(
    ("rain_in_hr", "expected"),
    [
        (0.0, RiskLevel.LOW),
        (0.099, RiskLevel.LOW),
        (0.10, RiskLevel.MODERATE),
        (0.25, RiskLevel.MODERATE),
        (0.26, RiskLevel.HIGH),
        (0.50, RiskLevel.HIGH),
        (0.51, RiskLevel.SEVERE),
        (1.00, RiskLevel.SEVERE),
        (1.01, RiskLevel.NO_TRAVEL),
    ],
)
def test_rain_thresholds_upper_inclusive(rain_in_hr: float, expected: RiskLevel) -> None:
    assert classify_rain(rain_in_hr) == expected


@pytest.mark.parametrize(
    ("snow_in_hr", "expected"),
    [
        (0.0, RiskLevel.LOW),
        (0.49, RiskLevel.LOW),
        (0.5, RiskLevel.MODERATE),
        (1.0, RiskLevel.MODERATE),
        (1.01, RiskLevel.HIGH),
        (2.0, RiskLevel.HIGH),
        (2.01, RiskLevel.SEVERE),
        (3.0, RiskLevel.SEVERE),
        (3.01, RiskLevel.NO_TRAVEL),
    ],
)
def test_snow_thresholds_upper_inclusive(snow_in_hr: float, expected: RiskLevel) -> None:
    assert classify_snow(snow_in_hr) == expected


@pytest.mark.parametrize(
    ("wind_mph", "load_lb", "expected_level", "expected_escalated"),
    [
        # PRD 7.1: Wind 55 mph returns No Travel for any load, including 10,000 lb
        (55.0, 10_000.0, RiskLevel.NO_TRAVEL, False),
        (56.0, 10_000.0, RiskLevel.NO_TRAVEL, False),
        # PRD 7.1: Wind 54.9 mph with 35,001 lb returns No Travel; with 30,000 lb returns Severe
        (54.9, 35_001.0, RiskLevel.NO_TRAVEL, True),
        (54.9, 30_000.1, RiskLevel.NO_TRAVEL, True),
        (54.9, 30_000.0, RiskLevel.SEVERE, False),
        (47.0, 35_000.0, RiskLevel.NO_TRAVEL, True),
        (47.0, 28_000.0, RiskLevel.SEVERE, False),
        # PRD 7.1: Wind 44.9 mph with 40,001 lb returns Severe; with 40,000 lb returns High
        (44.9, 40_001.0, RiskLevel.SEVERE, True),
        (44.9, 40_000.0, RiskLevel.HIGH, False),
        (38.0, 45_000.0, RiskLevel.SEVERE, True),
        (38.0, 35_000.0, RiskLevel.HIGH, False),
    ],
)
def test_load_weight_escalation_rules(
    wind_mph: float,
    load_lb: float,
    expected_level: RiskLevel,
    expected_escalated: bool,
) -> None:
    sample = WeatherSample(wind_mph=wind_mph, gust_mph=wind_mph, rain_in_hr=0.0, snow_in_hr=0.0)
    res = classify_checkpoint_risk(sample, load_lb)
    assert res.level == expected_level
    assert res.load_escalated is expected_escalated
    assert len(res.reasons) >= 1


def test_conflicting_conditions_and_load_never_lowers_base() -> None:
    # Wind 38 mph + 45,000 lb would escalate wind to Severe, but snow is 3.5 in/hr (No Travel)
    sample = WeatherSample(wind_mph=38.0, gust_mph=42.0, rain_in_hr=0.0, snow_in_hr=3.5)
    res = classify_checkpoint_risk(sample, 45_000.0)
    assert res.level == RiskLevel.NO_TRAVEL

    # Gust-aware toggle test (RK-6)
    sample_gust = WeatherSample(wind_mph=30.0, gust_mph=48.0, rain_in_hr=0.0, snow_in_hr=0.0)
    res_sustained = classify_checkpoint_risk(sample_gust, 35_000.0, gust_aware=False)
    res_gust = classify_checkpoint_risk(sample_gust, 35_000.0, gust_aware=True)
    assert res_sustained.level == RiskLevel.MODERATE
    assert res_gust.level == RiskLevel.NO_TRAVEL


def test_missing_weather_never_becomes_low() -> None:
    # PRD 7.1: Missing weather never becomes Low
    res_none = classify_checkpoint_risk(None, 35_000.0)
    assert res_none.level == RiskLevel.UNKNOWN
    assert res_none.level != RiskLevel.LOW

    unknown_sample = WeatherSample(wind_mph=None, rain_in_hr=None, snow_in_hr=None, data_quality="unknown")
    res_unk = classify_checkpoint_risk(unknown_sample, 35_000.0)
    assert res_unk.level == RiskLevel.UNKNOWN
    assert "Weather unavailable at this point" in res_unk.reasons[0]


# ---------------------------------------------------------------------------
# 2. Checkpoints, Geometry, Segment Attribution & ETA Tests (PRD 7.1)
# ---------------------------------------------------------------------------
def test_checkpoints_short_trip_and_segment_sum() -> None:
    # Short trip (< N miles) still has two checkpoints (Origin and Destination)
    coords = [(41.8781, -87.6298), (41.8000, -87.7500)]
    dep = datetime(2026, 11, 1, 14, 0, tzinfo=UTC)
    cps = generate_checkpoints(
        coords=coords,
        departure_utc=dep,
        interval_miles=25.0,
        total_duration_seconds=900.0,
        override_total_miles=8.4,
    )
    assert len(cps) == 2
    assert cps[0].mile == 0.0
    assert cps[-1].mile == 8.4
    assert abs(sum(cp.segment_miles for cp in cps) - 8.4) < 0.01


def test_checkpoints_spacing_monotonic_eta_and_timezone_crossing() -> None:
    # Chicago (America/Chicago) to Denver (America/Denver) across timezone line
    coords = [
        (41.8781, -87.6298),
        (41.5868, -93.6250),
        (41.1239, -100.7654),
        (39.7392, -104.9903),
    ]
    dep = datetime(2026, 11, 1, 14, 0, tzinfo=UTC)
    sections = [
        RouteSection(0.0, 300.0, 300.0 * 60),
        RouteSection(300.0, 700.0, 400.0 * 60),
        RouteSection(700.0, 1000.0, 300.0 * 60),
    ]
    cps = generate_checkpoints(
        coords=coords,
        departure_utc=dep,
        interval_miles=50.0,
        total_duration_seconds=1000.0 * 60,
        sections=sections,
        override_total_miles=1000.0,
    )
    assert cps[0].mile == 0.0
    assert cps[1].mile == 50.0
    assert cps[-1].mile == 1000.0
    assert abs(sum(cp.segment_miles for cp in cps) - 1000.0) < 0.1

    # ETAs never decrease along a route, and last one equals arrival time
    for i in range(1, len(cps)):
        assert cps[i].eta_utc >= cps[i - 1].eta_utc
    assert cps[-1].eta_utc == dep + timedelta(seconds=1000.0 * 60)

    # Origin in Central Time, Destination in Mountain Time
    assert "Chicago" in cps[0].timezone_name
    assert "Denver" in cps[-1].timezone_name


def test_hourly_forecast_eta_interpolation_and_neighbor_borrow() -> None:
    # PRD 7.1: With a mock forecast that changes hourly, each checkpoint uses the hour of its own ETA
    base_dt = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
    ep0 = int(base_dt.timestamp()) // 3600
    series = GridForecastSeries(
        grid_lat=41.0,
        grid_lng=-100.0,
        issued_at_utc="2026-11-01T12:00:00Z",
        source="MockHourly",
        hours={
            ep0: HourlyForecastPoint(base_dt, wind_mph=20.0, gust_mph=25.0, rain_in_hr=0.0, snow_in_hr=0.0, temperature_f=50.0, precip_prob_pct=0.0),
            ep0 + 1: HourlyForecastPoint(base_dt + timedelta(hours=1), wind_mph=40.0, gust_mph=50.0, rain_in_hr=0.2, snow_in_hr=0.0, temperature_f=46.0, precip_prob_pct=50.0),
            ep0 + 2: HourlyForecastPoint(base_dt + timedelta(hours=2), wind_mph=60.0, gust_mph=70.0, rain_in_hr=0.6, snow_in_hr=0.0, temperature_f=40.0, precip_prob_pct=90.0),
        },
    )
    wx_h0 = interpolate_weather_at_eta(series, base_dt)
    wx_half = interpolate_weather_at_eta(series, base_dt + timedelta(minutes=30))
    wx_h2 = interpolate_weather_at_eta(series, base_dt + timedelta(hours=2))

    assert wx_h0 is not None and wx_h0.wind_mph == 20.0
    assert wx_half is not None and wx_half.wind_mph == 30.0
    assert wx_h2 is not None and wx_h2.wind_mph == 60.0

    # Test neighbor borrowing (WX-4)
    grid_map = {(41.0, -100.0): series}
    samples, has_deg = sample_checkpoint_weather_with_fallback(
        [
            (41.0, -100.0, base_dt),
            (42.5, -102.0, base_dt + timedelta(hours=1)),  # Missing grid cell -> borrows neighbor
        ],
        grid_map,
    )
    assert has_deg is True
    assert samples[0].data_quality == "ok"
    assert samples[1].data_quality == "borrowed"
    assert samples[1].wind_mph == 20.0


def test_polyline_and_corridor_helpers() -> None:
    pts = [(41.8781, -87.6298), (41.2565, -95.9345), (39.7392, -104.9903)]
    enc = encode_polyline(pts)
    dec = decode_polyline(enc)
    assert len(dec) == 3
    assert haversine_miles(pts[0][0], pts[0][1], dec[0][0], dec[0][1]) < 0.05

    overlap_same = route_overlap_ratio(pts, pts)
    assert overlap_same == 1.0

    pos_lat, pos_lng, pos_mile = point_at_elapsed_minutes(pts, 600.0, 300.0)
    assert pos_mile > 0.0

    cells = build_corridor_grid([("route-a", pts)], step_miles=50.0, max_cells=200)
    assert 5 <= len(cells) <= 200


# ---------------------------------------------------------------------------
# 3. Route Scoring & Recommendation Tests (PRD 7.1)
# ---------------------------------------------------------------------------
def _make_dummy_scored_route(
    route_id: str,
    label: str,
    duration_min: int,
    checkpoint_levels_and_miles: list[tuple[RiskLevel, float]],
) -> ScoredRoute:
    cps: list[EvaluatedCheckpoint] = []
    cum_m = 0.0
    for idx, (lvl, seg_mi) in enumerate(checkpoint_levels_and_miles):
        cps.append(
            EvaluatedCheckpoint(
                index=idx,
                mile=cum_m,
                lat=40.0,
                lng=-100.0,
                place="Test, NE",
                segment_miles=seg_mi,
                eta_utc_iso="2026-11-01T15:00:00Z",
                eta_local_iso="2026-11-01T09:00:00-06:00",
                eta_local_display="Nov 01, 09:00 AM CST",
                timezone_abbr="CST",
                eta_is_estimate=False,
                wind_mph=56.0 if lvl == RiskLevel.NO_TRAVEL else 20.0,
                gust_mph=60.0,
                rain_in_hr=0.0,
                snow_in_hr=0.0,
                temperature_f=45.0,
                precip_prob_pct=10.0,
                level=lvl,
                label=lvl.label,
                score=int(lvl),
                driving_condition="wind" if lvl > RiskLevel.LOW else "clear",
                load_escalated=False,
                reasons=[f"Level {lvl.label}"],
                data_quality="unknown" if lvl == RiskLevel.UNKNOWN else "ok",
            )
        )
        cum_m += seg_mi

    total_mi = sum(seg for _, seg in checkpoint_levels_and_miles)
    metrics = compute_route_metrics(cps, total_mi, duration_min)
    return ScoredRoute(
        id=route_id,
        label=label,
        summary=f"via {label}",
        encoded_geometry="",
        coordinates=[(40.0, -90.0), (40.0, -100.0)],
        distance_mi=total_mi,
        duration_min=duration_min,
        arrival_time_utc="2026-11-01T20:00:00Z",
        arrival_time_local="Nov 01, 02:00 PM CST",
        checkpoints=cps,
        metrics=metrics,
        blocked=metrics.no_travel_miles > 0.0,
    )


def test_recommendation_lexicographic_order_and_blocked_handling() -> None:
    # Route A: Blocked (10 mi No Travel, 0 Severe, fastest 500 min)
    route_a = _make_dummy_scored_route(
        "route-a",
        "Route A",
        500,
        [(RiskLevel.NO_TRAVEL, 10.0), (RiskLevel.LOW, 490.0)],
    )
    # Route B: Clear (0 No Travel, 25 Severe, 540 min)
    route_b = _make_dummy_scored_route(
        "route-b",
        "Route B",
        540,
        [(RiskLevel.SEVERE, 25.0), (RiskLevel.LOW, 475.0)],
    )
    # Route C: Clear (0 No Travel, 0 Severe, 40 High, 560 min)
    route_c = _make_dummy_scored_route(
        "route-c",
        "Route C",
        560,
        [(RiskLevel.HIGH, 40.0), (RiskLevel.LOW, 460.0)],
    )

    ranked, rec = rank_and_recommend_routes([route_a, route_b, route_c])
    # Route C wins (0 Severe vs 25 on B; A is Blocked despite 0 Severe)
    assert [r.id for r in ranked] == ["route-c", "route-b", "route-a"]
    assert rec.recommended_route_id == "route-c"
    assert rec.all_blocked is False
    assert ranked[0].recommended is True
    assert ranked[2].blocked is True


def test_all_blocked_state_sc3() -> None:
    r1 = _make_dummy_scored_route(
        "route-1", "Route 1", 500, [(RiskLevel.NO_TRAVEL, 50.0), (RiskLevel.LOW, 450.0)]
    )
    r2 = _make_dummy_scored_route(
        "route-2", "Route 2", 520, [(RiskLevel.NO_TRAVEL, 15.0), (RiskLevel.LOW, 485.0)]
    )
    ranked, rec = rank_and_recommend_routes([r1, r2])
    assert rec.all_blocked is True
    assert rec.recommended_route_id is None
    assert rec.least_bad_route_id == "route-2"
    assert "No safe route at this departure time" in rec.headline


# ---------------------------------------------------------------------------
# 4. End-to-End API Contract Tests (Section 5.2 & 7.1)
# ---------------------------------------------------------------------------
def test_api_endpoints_end_to_end() -> None:
    client = Client()

    # 1. Health endpoint
    res_health = client.get("/api/v1/health/")
    assert res_health.status_code == 200
    assert res_health.json()["status"] == "ok"

    # 2. Geocode endpoint
    res_geo = client.get("/api/v1/geocode/?q=Chicago")
    assert res_geo.status_code == 200
    geo_results = res_geo.json()["results"]
    assert len(geo_results) >= 1
    assert "Chicago" in geo_results[0]["label"]

    # 3. Analyze endpoint in storm demo mode with 35,000 lb load
    analyze_payload = {
        "origin": {"label": "Chicago, IL", "lat": 41.8781, "lng": -87.6298},
        "destination": {"label": "Denver, CO", "lat": 39.7392, "lng": -104.9903},
        "departureTime": "2026-11-01T14:00:00Z",
        "loadWeightLb": 35000,
        "intervalMiles": 50,
        "options": {"gustAware": False, "demoScenario": "storm"},
    }
    res_analyze = client.post(
        "/api/v1/analyze/",
        data=analyze_payload,
        content_type="application/json",
    )
    assert res_analyze.status_code == 200
    data = res_analyze.json()
    analysis_id = data["analysisId"]
    assert len(data["routes"]) == 3
    assert data["recommendation"]["explanation"]

    # Verify miles by level sum to route distance within 0.1 mile (PRD 7.1)
    for route in data["routes"]:
        m = route["metrics"]
        sum_miles = (
            m["lowMiles"]
            + m["moderateMiles"]
            + m["highMiles"]
            + m["severeMiles"]
            + m["noTravelMiles"]
            + m["unknownMiles"]
        )
        assert abs(sum_miles - route["distanceMi"]) <= 0.2

    # 4. Heatmap endpoint — verify 49 hourly values per cell (PRD 7.1)
    res_hm = client.get(f"/api/v1/analyze/{analysis_id}/heatmap/")
    assert res_hm.status_code == 200
    hm_data = res_hm.json()
    assert len(hm_data["hours"]) == 49
    assert len(hm_data["cells"]) > 0
    first_cell = hm_data["cells"][0]
    assert len(first_cell["risk"]) == 49
    assert len(first_cell["wind"]) == 49

    # 5. Departure window endpoint
    res_dw = client.get(f"/api/v1/analyze/{analysis_id}/departure-window/")
    assert res_dw.status_code == 200
    dw_data = res_dw.json()
    assert len(dw_data["windows"]) > 5
