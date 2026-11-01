"""Route generation adapters, via-waypoint diversification, and <90% overlap deduplication (RT-1 to RT-5)."""

from .service import RawRouteCandidate, RoutingResult, generate_truck_routes

__all__ = [
    "RawRouteCandidate",
    "RoutingResult",
    "generate_truck_routes",
]
