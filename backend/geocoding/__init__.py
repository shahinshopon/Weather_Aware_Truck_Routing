"""Geocoding autocomplete and offline US nearest-place lookup (PRD Section 4.2, GC-1 to GC-4)."""

from .service import GeocodeSuggestion, geocode_autocomplete, nearest_place_label, resolve_place

__all__ = [
    "GeocodeSuggestion",
    "geocode_autocomplete",
    "resolve_place",
    "nearest_place_label",
]
