"""Deterministic route scoring, Blocked route logic, lexicographic ranking, and plain-language recommendation (SC-1 to SC-6)."""

from __future__ import annotations

from dataclasses import dataclass, field

from risk.config import RiskLevel


@dataclass(frozen=True)
class EvaluatedCheckpoint:
    """Checkpoint with segment distance, weather values, and evaluated risk."""

    index: int
    mile: float
    lat: float
    lng: float
    place: str
    segment_miles: float
    eta_utc_iso: str
    eta_local_iso: str
    eta_local_display: str
    timezone_abbr: str
    eta_is_estimate: bool
    wind_mph: float | None
    gust_mph: float | None
    rain_in_hr: float | None
    snow_in_hr: float | None
    temperature_f: float | None
    precip_prob_pct: float | None
    level: RiskLevel
    label: str
    score: int
    driving_condition: str
    load_escalated: bool
    reasons: list[str]
    data_quality: str = "ok"


@dataclass(frozen=True)
class RouteTradeoff:
    """SC-5: Per-route tradeoff versus the fastest route."""

    time_added_min: int
    severe_miles_saved: float
    high_miles_saved: float
    no_travel_miles_saved: float
    is_fastest: bool
    summary: str


@dataclass(frozen=True)
class RouteMetrics:
    """SC-1: Per-route rolled-up risk metrics."""

    total_miles: float
    duration_min: int
    miles_by_level: dict[str, float]
    low_miles: float
    moderate_miles: float
    high_miles: float
    severe_miles: float
    no_travel_miles: float
    unknown_miles: float
    avg_risk: float
    max_level: RiskLevel
    max_level_label: str
    worst_checkpoint_index: int
    worst_checkpoint_mile: float
    worst_checkpoint_place: str
    worst_checkpoint_reason: str
    no_travel_checkpoint_count: int
    has_unknown_weather: bool


@dataclass
class ScoredRoute:
    """Complete scored and ranked route option."""

    id: str
    label: str
    summary: str
    encoded_geometry: str
    coordinates: list[tuple[float, float]]
    distance_mi: float
    duration_min: int
    arrival_time_utc: str
    arrival_time_local: str
    checkpoints: list[EvaluatedCheckpoint]
    metrics: RouteMetrics
    blocked: bool
    blocked_reason: str | None = None
    rank: int = 1
    recommended: bool = False
    tradeoff: RouteTradeoff | None = None
    risk_segments: list[dict[str, object]] = field(default_factory=list)


@dataclass(frozen=True)
class RecommendationSummary:
    """SC-3, SC-4: Top-level recommendation result and explanation."""

    recommended_route_id: str | None
    recommended_route_label: str | None
    all_blocked: bool
    least_bad_route_id: str | None
    headline: str
    explanation: str
    reasons: list[str]


def compute_route_metrics(
    checkpoints: list[EvaluatedCheckpoint],
    total_miles: float,
    duration_min: int,
) -> RouteMetrics:
    """
    SC-1: Compute miles at each level (Low through No Travel), distance-weighted average risk,
    unknown miles, max level, worst checkpoint, and No Travel checkpoint count.
    """
    miles_map: dict[RiskLevel, float] = {
        RiskLevel.LOW: 0.0,
        RiskLevel.MODERATE: 0.0,
        RiskLevel.HIGH: 0.0,
        RiskLevel.SEVERE: 0.0,
        RiskLevel.NO_TRAVEL: 0.0,
        RiskLevel.UNKNOWN: 0.0,
    }

    weighted_score_sum = 0.0
    known_miles_sum = 0.0
    no_travel_count = 0

    worst_cp: EvaluatedCheckpoint | None = None
    max_level = RiskLevel.LOW

    for cp in checkpoints:
        seg = max(0.0, cp.segment_miles)
        lvl = cp.level
        miles_map[lvl] = miles_map.get(lvl, 0.0) + seg

        if lvl == RiskLevel.NO_TRAVEL:
            no_travel_count += 1

        if lvl != RiskLevel.UNKNOWN and cp.data_quality != "unknown":
            weighted_score_sum += seg * float(int(lvl))
            known_miles_sum += seg
            if lvl > max_level:
                max_level = lvl

        if worst_cp is None:
            worst_cp = cp
        else:
            # Prefer higher risk level; break ties by higher wind/rain/snow
            if cp.level > worst_cp.level or (
                cp.level == worst_cp.level
                and (cp.wind_mph or 0.0) > (worst_cp.wind_mph or 0.0)
            ):
                worst_cp = cp

    avg_risk = (
        round(weighted_score_sum / known_miles_sum, 3)
        if known_miles_sum > 1e-6
        else 0.0
    )

    low_mi = round(miles_map[RiskLevel.LOW], 1)
    mod_mi = round(miles_map[RiskLevel.MODERATE], 1)
    high_mi = round(miles_map[RiskLevel.HIGH], 1)
    sev_mi = round(miles_map[RiskLevel.SEVERE], 1)
    nt_mi = round(miles_map[RiskLevel.NO_TRAVEL], 1)
    unk_mi = round(miles_map[RiskLevel.UNKNOWN], 1)

    return RouteMetrics(
        total_miles=round(total_miles, 1),
        duration_min=duration_min,
        miles_by_level={
            "Low": low_mi,
            "Moderate": mod_mi,
            "High": high_mi,
            "Severe": sev_mi,
            "No Travel": nt_mi,
            "Unknown": unk_mi,
        },
        low_miles=low_mi,
        moderate_miles=mod_mi,
        high_miles=high_mi,
        severe_miles=sev_mi,
        no_travel_miles=nt_mi,
        unknown_miles=unk_mi,
        avg_risk=avg_risk,
        max_level=max_level,
        max_level_label=max_level.label,
        worst_checkpoint_index=worst_cp.index if worst_cp else 0,
        worst_checkpoint_mile=worst_cp.mile if worst_cp else 0.0,
        worst_checkpoint_place=worst_cp.place if worst_cp else "",
        worst_checkpoint_reason=(
            worst_cp.reasons[0] if (worst_cp and worst_cp.reasons) else "Clear conditions"
        ),
        no_travel_checkpoint_count=no_travel_count,
        has_unknown_weather=unk_mi > 0.0,
    )


def _route_sort_key(route: ScoredRoute, all_blocked: bool = False) -> tuple[int, float, float, float, float, int]:
    """
    SC-2: Strict lexicographic sort key:
    - Unblocked before Blocked (0 vs 1)
    - If all_blocked (or comparing two Blocked routes), fewest No Travel miles first
    - (1) Fewest Severe miles (0.1 mile precision)
    - (2) Fewest High miles (0.1 mile precision)
    - (3) Lowest average risk (0.01 precision)
    - (4) Shortest travel time (minutes)
    """
    m = route.metrics
    blocked_flag = 1 if route.blocked else 0
    no_travel_bucket = round(m.no_travel_miles, 1) if (route.blocked or all_blocked) else 0.0
    severe_bucket = round(m.severe_miles, 1)
    high_bucket = round(m.high_miles, 1)
    avg_risk_bucket = round(m.avg_risk, 2)
    return (
        blocked_flag,
        no_travel_bucket,
        severe_bucket,
        high_bucket,
        avg_risk_bucket,
        m.duration_min,
    )


def _build_tradeoff(route: ScoredRoute, fastest_route: ScoredRoute) -> RouteTradeoff:
    """SC-5: Compute time added and Severe/High miles saved versus the fastest route."""
    time_added = route.duration_min - fastest_route.duration_min
    sev_saved = round(fastest_route.metrics.severe_miles - route.metrics.severe_miles, 1)
    high_saved = round(fastest_route.metrics.high_miles - route.metrics.high_miles, 1)
    nt_saved = round(fastest_route.metrics.no_travel_miles - route.metrics.no_travel_miles, 1)
    is_fastest = route.id == fastest_route.id

    if is_fastest:
        summary = "Fastest route option"
    else:
        time_str = f"+{time_added} min" if time_added >= 0 else f"{time_added} min"
        savings_parts: list[str] = []
        if nt_saved > 0.1:
            savings_parts.append(f"avoids {nt_saved:.0f} No Travel mi")
        if sev_saved > 0.1:
            savings_parts.append(f"saves {sev_saved:.0f} Severe mi")
        if high_saved > 0.1:
            savings_parts.append(f"saves {high_saved:.0f} High mi")
        if savings_parts:
            summary = f"{time_str} vs. fastest · {', '.join(savings_parts)}"
        else:
            summary = f"{time_str} vs. fastest route"

    return RouteTradeoff(
        time_added_min=time_added,
        severe_miles_saved=sev_saved,
        high_miles_saved=high_saved,
        no_travel_miles_saved=nt_saved,
        is_fastest=is_fastest,
        summary=summary,
    )


def rank_and_recommend_routes(
    routes: list[ScoredRoute],
) -> tuple[list[ScoredRoute], RecommendationSummary]:
    """
    SC-2 to SC-5:
    Rank routes deterministically, mark Blocked routes, compute tradeoffs vs. fastest,
    and generate a plain-language recommendation with metric differences.
    """
    if not routes:
        return [], RecommendationSummary(
            recommended_route_id=None,
            recommended_route_label=None,
            all_blocked=False,
            least_bad_route_id=None,
            headline="No routes available",
            explanation="No drivable routes were returned for the selected origin and destination.",
            reasons=[],
        )

    # Mark Blocked status on any route containing No Travel miles
    for r in routes:
        if r.metrics.no_travel_miles > 0.0 or r.metrics.no_travel_checkpoint_count > 0:
            r.blocked = True
            nt_cp = next(
                (cp for cp in r.checkpoints if cp.level == RiskLevel.NO_TRAVEL),
                None,
            )
            if nt_cp and nt_cp.reasons:
                r.blocked_reason = (
                    f"Blocked ({r.metrics.no_travel_miles:.0f} mi No Travel): "
                    f"{nt_cp.reasons[0]} near {nt_cp.place} (Mile {nt_cp.mile:.0f})"
                )
            else:
                r.blocked_reason = f"Blocked: {r.metrics.no_travel_miles:.1f} miles of No Travel conditions"
        else:
            r.blocked = False
            r.blocked_reason = None

    all_blocked = all(r.blocked for r in routes)

    # Identify fastest route overall (and fastest clear route if available)
    fastest_route = min(routes, key=lambda r: (r.duration_min, r.distance_mi))

    # Sort routes by strict lexicographic order (SC-2)
    sorted_routes = sorted(routes, key=lambda r: _route_sort_key(r, all_blocked=all_blocked))

    for rank_idx, r in enumerate(sorted_routes, start=1):
        r.rank = rank_idx
        r.recommended = (rank_idx == 1) and (not all_blocked)
        r.tradeoff = _build_tradeoff(r, fastest_route)

    top = sorted_routes[0]

    # SC-3: Every route is Blocked
    if all_blocked:
        blocked_reasons = [
            f"All {len(sorted_routes)} route options encounter No Travel conditions at this departure time.",
            f"{top.label} ({top.summary}) is the least-bad option with {top.metrics.no_travel_miles:.1f} No Travel miles and {top.metrics.severe_miles:.1f} Severe miles.",
        ]
        if top.blocked_reason:
            blocked_reasons.append(top.blocked_reason)
        explanation = " ".join(blocked_reasons)
        return sorted_routes, RecommendationSummary(
            recommended_route_id=None,
            recommended_route_label=None,
            all_blocked=True,
            least_bad_route_id=top.id,
            headline="No safe route at this departure time",
            explanation=explanation,
            reasons=blocked_reasons,
        )

    # SC-4: Plain-language explanation of the pick with metric differences
    reasons: list[str] = []
    if len(sorted_routes) == 1:
        reasons.append(
            f"{top.label} ({top.summary}) is the only distinct route available "
            f"({top.metrics.severe_miles:.0f} Severe mi, {top.metrics.high_miles:.0f} High mi, avg risk {top.metrics.avg_risk:.2f})."
        )
    else:
        runner_up = sorted_routes[1]
        comparison_target = fastest_route if fastest_route.id != top.id else runner_up

        diff_clauses: list[str] = []
        if comparison_target.blocked:
            diff_clauses.append(
                f"avoids {comparison_target.metrics.no_travel_miles:.0f} No Travel miles on {comparison_target.label}"
            )
        if round(top.metrics.severe_miles, 1) < round(comparison_target.metrics.severe_miles, 1):
            diff_clauses.append(
                f"has {top.metrics.severe_miles:.0f} Severe miles versus {comparison_target.metrics.severe_miles:.0f} on {comparison_target.label}"
            )
        if round(top.metrics.high_miles, 1) < round(comparison_target.metrics.high_miles, 1):
            diff_clauses.append(
                f"has {top.metrics.high_miles:.0f} High miles versus {comparison_target.metrics.high_miles:.0f} on {comparison_target.label}"
            )
        if round(top.metrics.avg_risk, 2) < round(comparison_target.metrics.avg_risk, 2):
            diff_clauses.append(
                f"lowers average risk to {top.metrics.avg_risk:.2f} vs. {comparison_target.metrics.avg_risk:.2f} on {comparison_target.label}"
            )

        time_diff = top.duration_min - fastest_route.duration_min
        if time_diff == 0:
            time_clause = f"is also the fastest route ({top.duration_min} min)"
        else:
            time_clause = f"adds {time_diff} minutes compared to the fastest route ({fastest_route.label})"

        if diff_clauses:
            primary_sentence = (
                f"{top.label} ({top.summary}) {' and '.join(diff_clauses[:2])}, and {time_clause}."
            )
        else:
            primary_sentence = (
                f"{top.label} ({top.summary}) ties on weather risk ({top.metrics.severe_miles:.0f} Severe mi, "
                f"{top.metrics.high_miles:.0f} High mi, avg risk {top.metrics.avg_risk:.2f}) and wins on shortest travel time ({top.duration_min} min)."
            )
        reasons.append(primary_sentence)

        # Add secondary runner-up detail if there are 3 routes
        for other in sorted_routes[1:]:
            if other.blocked:
                reasons.append(
                    f"{other.label} is Blocked due to {other.metrics.no_travel_miles:.0f} miles of No Travel conditions."
                )
            else:
                reasons.append(
                    f"Compared to {other.label}: {top.metrics.severe_miles:.0f} vs {other.metrics.severe_miles:.0f} Severe mi, "
                    f"{top.metrics.high_miles:.0f} vs {other.metrics.high_miles:.0f} High mi, "
                    f"avg risk {top.metrics.avg_risk:.2f} vs {other.metrics.avg_risk:.2f}."
                )

    headline = f"Recommended: {top.label} ({top.summary})"
    return sorted_routes, RecommendationSummary(
        recommended_route_id=top.id,
        recommended_route_label=top.label,
        all_blocked=False,
        least_bad_route_id=top.id,
        headline=headline,
        explanation=reasons[0],
        reasons=reasons,
    )
