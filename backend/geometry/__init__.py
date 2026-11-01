"""Geometry, checkpoint placement, ETA interpolation, and corridor grid utilities."""

from .checkpoints import (
    CheckpointGeometry,
    RouteSection,
    assign_segment_miles,
    build_corridor_grid,
    decode_polyline,
    encode_polyline,
    format_local_eta,
    generate_checkpoints,
    get_timezone_name,
    haversine_miles,
    point_at_elapsed_minutes,
    route_overlap_ratio,
)

__all__ = [
    "CheckpointGeometry",
    "RouteSection",
    "haversine_miles",
    "encode_polyline",
    "decode_polyline",
    "generate_checkpoints",
    "assign_segment_miles",
    "get_timezone_name",
    "format_local_eta",
    "point_at_elapsed_minutes",
    "route_overlap_ratio",
    "build_corridor_grid",
]
