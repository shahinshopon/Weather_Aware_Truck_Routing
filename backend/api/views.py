"""REST API views implementing Section 5.2 API contract."""

from __future__ import annotations

from datetime import UTC, datetime

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from analysis.orchestrator import (
    AnalysisError,
    build_departure_window_scan,
    build_heatmap_payload,
    run_trip_analysis,
)
from geocoding.service import geocode_autocomplete
from risk.config import (
    LOAD_LIMIT_NO_TRAVEL_LB,
    LOAD_LIMIT_SEVERE_LB,
    LOAD_SOFT_WARNING_LB,
    RAIN_THRESHOLDS,
    SNOW_THRESHOLDS,
    WIND_THRESHOLDS,
)

from .serializers import AnalyzeRequestSerializer


class HealthView(APIView):
    """GET /api/v1/health/ — Uptime and warm-up check."""

    @extend_schema(summary="Health and threshold config check")
    def get(self, request: Request) -> Response:
        return Response(
            {
                "status": "ok",
                "timestamp": datetime.now(UTC).isoformat(),
                "thresholds": {
                    "windMph": WIND_THRESHOLDS,
                    "rainInHr": RAIN_THRESHOLDS,
                    "snowInHr": SNOW_THRESHOLDS,
                    "loadLimitsLb": {
                        "noTravelWind45To55": LOAD_LIMIT_NO_TRAVEL_LB,
                        "severeWind35To45": LOAD_LIMIT_SEVERE_LB,
                        "softWarningGross": LOAD_SOFT_WARNING_LB,
                    },
                },
            },
            status=status.HTTP_200_OK,
        )


class GeocodeView(APIView):
    """GET /api/v1/geocode/?q= — US-biased autocomplete suggestions."""

    @extend_schema(
        summary="Location autocomplete suggestions",
        parameters=[
            OpenApiParameter(
                name="q",
                description="Search query (minimum 2 characters)",
                required=True,
                type=str,
            )
        ],
    )
    def get(self, request: Request) -> Response:
        query = str(request.query_params.get("q") or "").strip()
        if len(query) < 2:
            return Response({"results": []}, status=status.HTTP_200_OK)

        suggestions = geocode_autocomplete(query, limit=6)
        return Response(
            {
                "results": [
                    {
                        "label": s.label,
                        "lat": s.lat,
                        "lng": s.lng,
                        "state": s.state,
                        "country": s.country,
                    }
                    for s in suggestions
                ]
            },
            status=status.HTTP_200_OK,
        )


class AnalyzeView(APIView):
    """POST /api/v1/analyze/ — Generate routes, sample ETA weather, score risk, and recommend route."""

    @extend_schema(
        summary="Analyze truck routes for weather risk and cargo load rules",
        request=AnalyzeRequestSerializer,
    )
    def post(self, request: Request) -> Response:
        serializer = AnalyzeRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "error": "Invalid trip parameters.",
                    "fieldErrors": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        valid = serializer.validated_data
        try:
            result = run_trip_analysis(
                origin_input=dict(valid["origin"]),
                destination_input=dict(valid["destination"]),
                departure_time_iso=str(valid["departureTime"]),
                load_weight_lb=float(valid["loadWeightLb"]),
                interval_miles=int(valid.get("intervalMiles", 25)),
                options=dict(valid.get("options") or {}),
            )
            return Response(result, status=status.HTTP_200_OK)
        except AnalysisError as exc:
            return Response(
                {
                    "error": exc.message,
                    "fieldErrors": exc.field_errors,
                },
                status=exc.status_code,
            )


class HeatmapView(APIView):
    """GET /api/v1/analyze/{id}/heatmap/ — Compact 0-48h weather risk grid for corridor."""

    @extend_schema(summary="Fetch 0-48h corridor heatmap grid for an analysis")
    def get(self, request: Request, analysis_id: str) -> Response:
        try:
            payload = build_heatmap_payload(analysis_id)
            return Response(payload, status=status.HTTP_200_OK)
        except AnalysisError as exc:
            return Response({"error": exc.message}, status=exc.status_code)


class DepartureWindowView(APIView):
    """GET /api/v1/analyze/{id}/departure-window/ — Re-score routes across ±12h departure offsets."""

    @extend_schema(summary="Scan alternative departure windows using cached 48h forecast")
    def get(self, request: Request, analysis_id: str) -> Response:
        try:
            payload = build_departure_window_scan(analysis_id)
            return Response(payload, status=status.HTTP_200_OK)
        except AnalysisError as exc:
            return Response({"error": exc.message}, status=exc.status_code)
