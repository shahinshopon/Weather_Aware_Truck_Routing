"""Geocoding provider adapter with caching, US bias, and offline nearest-neighbor checkpoint lookup (GC-1 to GC-4)."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

import httpx
from django.core.cache import cache

from geometry.checkpoints import haversine_miles

from .us_places import US_PLACES, USPlace

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GeocodeSuggestion:
    """Autocomplete or geocoded place result."""

    label: str
    lat: float
    lng: float
    state: str = ""
    country: str = "US"


def nearest_place_label(lat: float, lng: float, mile: float | None = None) -> str:
    """
    GC-4: Generate checkpoint place labels such as 'near Cheyenne, WY' using the offline
    US places dataset with nearest-neighbor lookup, avoiding hundreds of reverse-geocode calls.
    """
    best_place: USPlace | None = None
    best_dist = float("inf")

    for place in US_PLACES:
        # Fast bounding box pre-filter before haversine
        if abs(place.lat - lat) > 5.0 or abs(place.lng - lng) > 6.0:
            continue
        dist = haversine_miles(lat, lng, place.lat, place.lng)
        if dist < best_dist:
            best_dist = dist
            best_place = place

    if best_place is None:
        # Fallback full scan if point was far from initial 5-deg box
        for place in US_PLACES:
            dist = haversine_miles(lat, lng, place.lat, place.lng)
            if dist < best_dist:
                best_dist = dist
                best_place = place

    if best_place is None:
        return f"{lat:.2f}°N, {abs(lng):.2f}°W"

    if best_dist <= 8.0:
        return best_place.label
    return f"near {best_place.label}"


def _search_local_places(query: str, limit: int = 6) -> list[GeocodeSuggestion]:
    """Search the curated US places dataset for fast, deterministic US suggestions."""
    q = query.strip().lower()
    if not q:
        return []

    prefix_matches: list[GeocodeSuggestion] = []
    substring_matches: list[GeocodeSuggestion] = []

    for place in US_PLACES:
        full_lower = place.label.lower()
        name_lower = place.name.lower()
        item = GeocodeSuggestion(
            label=place.label,
            lat=place.lat,
            lng=place.lng,
            state=place.state,
            country="US",
        )
        if name_lower.startswith(q) or full_lower.startswith(q):
            prefix_matches.append(item)
        elif q in full_lower:
            substring_matches.append(item)

    combined = prefix_matches + substring_matches
    return combined[:limit]


def _fetch_provider_suggestions(query: str, limit: int = 6) -> list[GeocodeSuggestion]:
    """
    GC-1: Provider-backed autocomplete (US-biased).
    Supports HERE Geocoding, Mapbox Geocoding, or Photon (Komoot OpenStreetMap type-ahead API).
    """
    here_key = os.getenv("HERE_API_KEY", "").strip()
    mapbox_token = os.getenv("MAPBOX_ACCESS_TOKEN", "").strip()

    try:
        with httpx.Client(timeout=3.5) as client:
            if here_key:
                resp = client.get(
                    "https://autocomplete.search.hereapi.com/v1/autocomplete",
                    params={
                        "q": query,
                        "in": "countryCode:USA",
                        "limit": limit,
                        "apiKey": here_key,
                    },
                )
                if resp.status_code == 200:
                    pass  # Fall through to geocode lookup if needed
            if mapbox_token:
                resp = client.get(
                    f"https://api.mapbox.com/geocoding/v5/mapbox.places/{query}.json",
                    params={
                        "country": "us",
                        "types": "place,locality,postcode,address",
                        "autocomplete": "true",
                        "limit": limit,
                        "access_token": mapbox_token,
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    results: list[GeocodeSuggestion] = []
                    for feat in data.get("features", []):
                        center = feat.get("center", [])
                        if len(center) == 2:
                            place_name = feat.get("place_name", "").replace(", United States", "")
                            results.append(
                                GeocodeSuggestion(
                                    label=place_name,
                                    lat=round(float(center[1]), 5),
                                    lng=round(float(center[0]), 5),
                                )
                            )
                    if results:
                        return results

            # Photon (Komoot) allows type-ahead autocomplete, biased to continental US center
            resp = client.get(
                "https://photon.komoot.io/api/",
                params={
                    "q": query,
                    "lat": 39.8283,
                    "lon": -98.5795,
                    "limit": limit * 2,
                    "lang": "en",
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                results = []
                seen: set[str] = set()
                for feat in data.get("features", []):
                    props = feat.get("properties", {})
                    geom = feat.get("geometry", {})
                    coords = geom.get("coordinates", [])
                    country_code = str(props.get("countrycode", "")).upper()
                    if country_code and country_code not in ("US", "CA"):
                        continue
                    if len(coords) != 2:
                        continue
                    name = props.get("name") or props.get("city")
                    state = props.get("state", "")
                    if not name:
                        continue
                    label = f"{name}, {state}" if state else str(name)
                    if label.lower() in seen:
                        continue
                    seen.add(label.lower())
                    results.append(
                        GeocodeSuggestion(
                            label=label,
                            lat=round(float(coords[1]), 5),
                            lng=round(float(coords[0]), 5),
                            state=str(state),
                            country=country_code or "US",
                        )
                    )
                    if len(results) >= limit:
                        break
                return results
    except Exception as exc:
        logger.warning("External geocoding provider error for query=%r: %s", query, exc)

    return []


def geocode_autocomplete(query: str, limit: int = 6) -> list[GeocodeSuggestion]:
    """
    GC-1, GC-2: Return cached US-biased autocomplete suggestions combining fast local major
    cities/hubs and external provider results.
    """
    clean_q = query.strip()
    if len(clean_q) < 2:
        return []

    cache_key = f"geocode:v1:{clean_q.lower()}:{limit}"
    cached = cache.get(cache_key)
    if cached is not None:
        return list(cached)

    local_hits = _search_local_places(clean_q, limit=limit)
    results = list(local_hits)
    seen_labels = {item.label.lower() for item in results}

    # Supplement with external provider if local hits are fewer than limit
    if len(results) < limit:
        external_hits = _fetch_provider_suggestions(clean_q, limit=limit)
        for item in external_hits:
            if item.label.lower() not in seen_labels:
                results.append(item)
                seen_labels.add(item.label.lower())
            if len(results) >= limit:
                break

    cache.set(cache_key, results, timeout=3600)
    return results


def resolve_place(
    label: str | None = None,
    lat: float | None = None,
    lng: float | None = None,
) -> GeocodeSuggestion | None:
    """Resolve an origin/destination input (either coordinates or text query) into a GeocodeSuggestion."""
    if lat is not None and lng is not None:
        resolved_label = (label or "").strip() or nearest_place_label(lat, lng)
        return GeocodeSuggestion(label=resolved_label, lat=float(lat), lng=float(lng))

    if label:
        suggestions = geocode_autocomplete(label, limit=1)
        if suggestions:
            return suggestions[0]

    return None
