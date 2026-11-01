"""Weather provider adapter, grid cache, linear ETA interpolation, and synthetic storm demo mode (WX-1 to WX-6, CP-3, UX-6)."""

from .service import (
    GridForecastSeries,
    HourlyForecastPoint,
    fetch_grid_forecasts,
    interpolate_weather_at_eta,
    sample_checkpoint_weather_with_fallback,
)

__all__ = [
    "HourlyForecastPoint",
    "GridForecastSeries",
    "fetch_grid_forecasts",
    "interpolate_weather_at_eta",
    "sample_checkpoint_weather_with_fallback",
]
