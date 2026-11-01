"""Route scoring, lexicographic ranking, and plain-language recommendation engine (PRD Section 4.7)."""

from .scorer import (
    EvaluatedCheckpoint,
    RecommendationSummary,
    RouteMetrics,
    RouteTradeoff,
    ScoredRoute,
    compute_route_metrics,
    rank_and_recommend_routes,
)

__all__ = [
    "EvaluatedCheckpoint",
    "RouteMetrics",
    "RouteTradeoff",
    "ScoredRoute",
    "RecommendationSummary",
    "compute_route_metrics",
    "rank_and_recommend_routes",
]
