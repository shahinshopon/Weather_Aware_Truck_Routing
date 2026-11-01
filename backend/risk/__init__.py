"""Pure risk and load-weight classification engine (PRD Section 4.6)."""

from .config import (
    LOAD_LIMIT_NO_TRAVEL_LB,
    LOAD_LIMIT_SEVERE_LB,
    RAIN_THRESHOLDS,
    SNOW_THRESHOLDS,
    WIND_THRESHOLDS,
    RiskLevel,
)
from .engine import (
    CheckpointRiskResult,
    WeatherSample,
    classify_checkpoint_risk,
    classify_rain,
    classify_snow,
    classify_wind,
)

__all__ = [
    "RiskLevel",
    "WIND_THRESHOLDS",
    "RAIN_THRESHOLDS",
    "SNOW_THRESHOLDS",
    "LOAD_LIMIT_NO_TRAVEL_LB",
    "LOAD_LIMIT_SEVERE_LB",
    "WeatherSample",
    "CheckpointRiskResult",
    "classify_wind",
    "classify_rain",
    "classify_snow",
    "classify_checkpoint_risk",
]
