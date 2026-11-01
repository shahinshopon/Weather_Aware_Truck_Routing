"""Deterministic risk and load-weight classification engine (PRD Section 4.6, RK-1 to RK-6)."""

from dataclasses import dataclass, field

from .config import (
    LOAD_LIMIT_NO_TRAVEL_LB,
    LOAD_LIMIT_SEVERE_LB,
    RAIN_HIGH_MAX_INCLUSIVE_IN_HR,
    RAIN_LOW_MAX_EXCLUSIVE_IN_HR,
    RAIN_MODERATE_MAX_INCLUSIVE_IN_HR,
    RAIN_SEVERE_MAX_INCLUSIVE_IN_HR,
    SNOW_HIGH_MAX_INCLUSIVE_IN_HR,
    SNOW_LOW_MAX_EXCLUSIVE_IN_HR,
    SNOW_MODERATE_MAX_INCLUSIVE_IN_HR,
    SNOW_SEVERE_MAX_INCLUSIVE_IN_HR,
    WIND_HIGH_MIN_MPH,
    WIND_MODERATE_MIN_MPH,
    WIND_NO_TRAVEL_MIN_MPH,
    WIND_SEVERE_MIN_MPH,
    RiskLevel,
)


@dataclass(frozen=True)
class WeatherSample:
    """Weather observation/forecast at a checkpoint or grid cell."""

    wind_mph: float | None = None
    gust_mph: float | None = None
    rain_in_hr: float | None = None
    snow_in_hr: float | None = None
    temperature_f: float | None = None
    precip_prob_pct: float | None = None
    data_quality: str = "ok"  # "ok" | "borrowed" | "unknown"


@dataclass(frozen=True)
class CheckpointRiskResult:
    """Result of classifying a checkpoint's weather and cargo load."""

    level: RiskLevel
    label: str
    score: int
    driving_condition: str
    wind_level: RiskLevel
    rain_level: RiskLevel
    snow_level: RiskLevel
    load_escalated: bool
    effective_wind_mph: float | None
    reasons: list[str] = field(default_factory=list)
    data_quality: str = "ok"


def classify_wind(wind_mph: float) -> RiskLevel:
    """
    Classify wind speed (mph) using lower-inclusive bounds:
    - < 25.0: Low
    - 25.0 to < 35.0: Moderate
    - 35.0 to < 45.0: High
    - 45.0 to < 55.0: Severe
    - >= 55.0: No Travel
    """
    if wind_mph >= WIND_NO_TRAVEL_MIN_MPH:
        return RiskLevel.NO_TRAVEL
    if wind_mph >= WIND_SEVERE_MIN_MPH:
        return RiskLevel.SEVERE
    if wind_mph >= WIND_HIGH_MIN_MPH:
        return RiskLevel.HIGH
    if wind_mph >= WIND_MODERATE_MIN_MPH:
        return RiskLevel.MODERATE
    return RiskLevel.LOW


def classify_rain(rain_in_hr: float) -> RiskLevel:
    """
    Classify rain rate (in/hr) using upper-inclusive bounds for Moderate/High/Severe:
    - < 0.10: Low
    - 0.10 to 0.25: Moderate
    - > 0.25 to 0.50: High
    - > 0.50 to 1.00: Severe
    - > 1.00: No Travel
    """
    if rain_in_hr > RAIN_SEVERE_MAX_INCLUSIVE_IN_HR:
        return RiskLevel.NO_TRAVEL
    if rain_in_hr > RAIN_HIGH_MAX_INCLUSIVE_IN_HR:
        return RiskLevel.SEVERE
    if rain_in_hr > RAIN_MODERATE_MAX_INCLUSIVE_IN_HR:
        return RiskLevel.HIGH
    if rain_in_hr >= RAIN_LOW_MAX_EXCLUSIVE_IN_HR:
        return RiskLevel.MODERATE
    return RiskLevel.LOW


def classify_snow(snow_in_hr: float) -> RiskLevel:
    """
    Classify snowfall rate (in/hr) using upper-inclusive bounds for Moderate/High/Severe:
    - < 0.5: Low
    - 0.5 to 1.0: Moderate
    - > 1.0 to 2.0: High
    - > 2.0 to 3.0: Severe
    - > 3.0: No Travel
    """
    if snow_in_hr > SNOW_SEVERE_MAX_INCLUSIVE_IN_HR:
        return RiskLevel.NO_TRAVEL
    if snow_in_hr > SNOW_HIGH_MAX_INCLUSIVE_IN_HR:
        return RiskLevel.SEVERE
    if snow_in_hr > SNOW_MODERATE_MAX_INCLUSIVE_IN_HR:
        return RiskLevel.HIGH
    if snow_in_hr >= SNOW_LOW_MAX_EXCLUSIVE_IN_HR:
        return RiskLevel.MODERATE
    return RiskLevel.LOW


def classify_checkpoint_risk(
    weather: WeatherSample | None,
    load_weight_lb: float,
    *,
    gust_aware: bool = False,
) -> CheckpointRiskResult:
    """
    Classify a checkpoint's weather and apply cargo load-weight escalation rules (RK-1 to RK-6).
    Never classifies missing/unknown weather as Low (WX-4).
    """
    if (
        weather is None
        or weather.data_quality == "unknown"
        or weather.wind_mph is None
        or weather.rain_in_hr is None
        or weather.snow_in_hr is None
    ):
        return CheckpointRiskResult(
            level=RiskLevel.UNKNOWN,
            label=RiskLevel.UNKNOWN.label,
            score=int(RiskLevel.UNKNOWN),
            driving_condition="unknown",
            wind_level=RiskLevel.UNKNOWN,
            rain_level=RiskLevel.UNKNOWN,
            snow_level=RiskLevel.UNKNOWN,
            load_escalated=False,
            effective_wind_mph=None,
            reasons=["Weather unavailable at this point"],
            data_quality="unknown",
        )

    effective_wind = weather.wind_mph
    if gust_aware and weather.gust_mph is not None:
        effective_wind = max(weather.wind_mph, weather.gust_mph)

    wind_level = classify_wind(effective_wind)
    rain_level = classify_rain(weather.rain_in_hr)
    snow_level = classify_snow(weather.snow_in_hr)

    # RK-1: Base level is the worst of wind, rain, and snow
    base_level = max(wind_level, rain_level, snow_level)

    # Determine primary driving condition for base level
    condition_pairs = [
        ("wind", wind_level),
        ("rain", rain_level),
        ("snow", snow_level),
    ]
    driving_condition = max(condition_pairs, key=lambda item: item[1])[0]

    final_level = base_level
    load_escalated = False
    reasons: list[str] = []

    # RK-2: Apply load rules after base level; they can only escalate
    # (a) Wind >= 55 mph is No Travel for any load
    if effective_wind >= WIND_NO_TRAVEL_MIN_MPH:
        final_level = max(final_level, RiskLevel.NO_TRAVEL)
        driving_condition = "wind"
        reasons.append(
            f"Wind {effective_wind:.1f} mph (55+ mph threshold): No Travel for any load"
        )
    # (b) Wind 45 to < 55 mph with load > 30,000 lb is No Travel
    elif (
        WIND_SEVERE_MIN_MPH <= effective_wind < WIND_NO_TRAVEL_MIN_MPH
        and load_weight_lb > LOAD_LIMIT_NO_TRAVEL_LB
    ):
        if final_level < RiskLevel.NO_TRAVEL:
            load_escalated = True
        final_level = max(final_level, RiskLevel.NO_TRAVEL)
        driving_condition = "wind"
        reasons.append(
            f"Wind {effective_wind:.1f} mph with {load_weight_lb:,.0f} lb load, "
            f"over the {LOAD_LIMIT_NO_TRAVEL_LB:,.0f} lb limit: No Travel"
        )
    # (c) Wind 35 to < 45 mph with load > 40,000 lb is Severe (or higher if base is already higher)
    elif (
        WIND_HIGH_MIN_MPH <= effective_wind < WIND_SEVERE_MIN_MPH
        and load_weight_lb > LOAD_LIMIT_SEVERE_LB
    ):
        if final_level < RiskLevel.SEVERE:
            load_escalated = True
            driving_condition = "wind"
        final_level = max(final_level, RiskLevel.SEVERE)
        reasons.append(
            f"Wind {effective_wind:.1f} mph with {load_weight_lb:,.0f} lb load, "
            f"over the {LOAD_LIMIT_SEVERE_LB:,.0f} lb limit: Severe"
        )

    # Add explanations for non-low base conditions that were not already explained by load rules
    if wind_level > RiskLevel.LOW and not reasons:
        wind_desc = "gust-adjusted wind" if (gust_aware and weather.gust_mph and weather.gust_mph > weather.wind_mph) else "Wind"
        reasons.append(f"{wind_desc} {effective_wind:.1f} mph: {wind_level.label}")

    if rain_level > RiskLevel.LOW:
        reasons.append(f"Rain {weather.rain_in_hr:.2f} in/hr: {rain_level.label}")

    if snow_level > RiskLevel.LOW:
        reasons.append(f"Snow {weather.snow_in_hr:.2f} in/hr: {snow_level.label}")

    if not reasons:
        reasons.append(
            f"Calm conditions (wind {effective_wind:.1f} mph, "
            f"rain {weather.rain_in_hr:.2f} in/hr, snow {weather.snow_in_hr:.2f} in/hr): Low"
        )

    if weather.data_quality == "borrowed":
        reasons.append("Weather borrowed from nearest neighbor checkpoint")

    return CheckpointRiskResult(
        level=final_level,
        label=final_level.label,
        score=int(final_level),
        driving_condition=driving_condition if final_level > RiskLevel.LOW else "clear",
        wind_level=wind_level,
        rain_level=rain_level,
        snow_level=snow_level,
        load_escalated=load_escalated,
        effective_wind_mph=round(effective_wind, 1),
        reasons=reasons,
        data_quality=weather.data_quality,
    )
