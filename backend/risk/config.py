"""Single source of truth for weather risk thresholds and load limits (PRD RK-5)."""

from enum import IntEnum


class RiskLevel(IntEnum):
    """Numeric risk scores from Low (0) to No Travel (4), plus UNKNOWN (-1) for missing data."""

    UNKNOWN = -1
    LOW = 0
    MODERATE = 1
    HIGH = 2
    SEVERE = 3
    NO_TRAVEL = 4

    @property
    def label(self) -> str:
        labels = {
            RiskLevel.UNKNOWN: "Unknown",
            RiskLevel.LOW: "Low",
            RiskLevel.MODERATE: "Moderate",
            RiskLevel.HIGH: "High",
            RiskLevel.SEVERE: "Severe",
            RiskLevel.NO_TRAVEL: "No Travel",
        }
        return labels[self]


# Wind (mph) — lower-inclusive bounds: [min, max)
# Low: < 25.0
# Moderate: 25.0 to < 35.0
# High: 35.0 to < 45.0
# Severe: 45.0 to < 55.0
# No Travel: >= 55.0
WIND_MODERATE_MIN_MPH: float = 25.0
WIND_HIGH_MIN_MPH: float = 35.0
WIND_SEVERE_MIN_MPH: float = 45.0
WIND_NO_TRAVEL_MIN_MPH: float = 55.0

WIND_THRESHOLDS = {
    "moderate_min": WIND_MODERATE_MIN_MPH,
    "high_min": WIND_HIGH_MIN_MPH,
    "severe_min": WIND_SEVERE_MIN_MPH,
    "no_travel_min": WIND_NO_TRAVEL_MIN_MPH,
}

# Rain (in/hr) — upper-inclusive bounds for Moderate/High/Severe so "over 1.00" is exact:
# Low: < 0.10
# Moderate: 0.10 to 0.25 (0.10 <= r <= 0.25)
# High: > 0.25 to 0.50 (0.25 < r <= 0.50)
# Severe: > 0.50 to 1.00 (0.50 < r <= 1.00)
# No Travel: > 1.00
RAIN_LOW_MAX_EXCLUSIVE_IN_HR: float = 0.10
RAIN_MODERATE_MAX_INCLUSIVE_IN_HR: float = 0.25
RAIN_HIGH_MAX_INCLUSIVE_IN_HR: float = 0.50
RAIN_SEVERE_MAX_INCLUSIVE_IN_HR: float = 1.00

RAIN_THRESHOLDS = {
    "low_max_exclusive": RAIN_LOW_MAX_EXCLUSIVE_IN_HR,
    "moderate_max_inclusive": RAIN_MODERATE_MAX_INCLUSIVE_IN_HR,
    "high_max_inclusive": RAIN_HIGH_MAX_INCLUSIVE_IN_HR,
    "severe_max_inclusive": RAIN_SEVERE_MAX_INCLUSIVE_IN_HR,
}

# Snow (in/hr) — upper-inclusive bounds for Moderate/High/Severe so "over 3.0" is exact:
# Low: < 0.5
# Moderate: 0.5 to 1.0 (0.5 <= s <= 1.0)
# High: > 1.0 to 2.0 (1.0 < s <= 2.0)
# Severe: > 2.0 to 3.0 (2.0 < s <= 3.0)
# No Travel: > 3.0
SNOW_LOW_MAX_EXCLUSIVE_IN_HR: float = 0.5
SNOW_MODERATE_MAX_INCLUSIVE_IN_HR: float = 1.0
SNOW_HIGH_MAX_INCLUSIVE_IN_HR: float = 2.0
SNOW_SEVERE_MAX_INCLUSIVE_IN_HR: float = 3.0

SNOW_THRESHOLDS = {
    "low_max_exclusive": SNOW_LOW_MAX_EXCLUSIVE_IN_HR,
    "moderate_max_inclusive": SNOW_MODERATE_MAX_INCLUSIVE_IN_HR,
    "high_max_inclusive": SNOW_HIGH_MAX_INCLUSIVE_IN_HR,
    "severe_max_inclusive": SNOW_SEVERE_MAX_INCLUSIVE_IN_HR,
}

# Cargo load weight limits (lb) — strictly greater than (>)
LOAD_LIMIT_NO_TRAVEL_LB: float = 30_000.0  # Wind [45, 55) + load > 30,000 lb -> No Travel
LOAD_LIMIT_SEVERE_LB: float = 40_000.0     # Wind [35, 45) + load > 40,000 lb -> Severe
LOAD_SOFT_WARNING_LB: float = 80_000.0     # Soft UI/API warning above typical US gross limit
