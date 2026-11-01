"""API v1 URL routes (PRD Section 5.2)."""

from django.urls import path

from .views import (
    AnalyzeView,
    DepartureWindowView,
    GeocodeView,
    HealthView,
    HeatmapView,
)

urlpatterns = [
    path("health/", HealthView.as_view(), name="api-health"),
    path("geocode/", GeocodeView.as_view(), name="api-geocode"),
    path("analyze/", AnalyzeView.as_view(), name="api-analyze"),
    path("analyze/<str:analysis_id>/heatmap/", HeatmapView.as_view(), name="api-heatmap"),
    path(
        "analyze/<str:analysis_id>/departure-window/",
        DepartureWindowView.as_view(),
        name="api-departure-window",
    ),
]
