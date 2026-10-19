"""OpenRouteService HTTP client: geocoding and truck directions.

The API key travels only in the Authorization header (never in URLs) and is
never logged or included in raised errors.
"""

import hashlib
import logging
import math
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx
from django.conf import settings
from django.core.cache import cache

from routes.errors import (
    ProviderLimitExceeded,
    LocationNotRoutable,
    RouteNotFound,
    RoutingDataError,
    RoutingNotConfigured,
    RoutingTimeout,
    RoutingUnavailable,
)
from routes.geometry import LatLng, validate_geometry

logger = logging.getLogger(__name__)

METERS_PER_MILE = 1609.344
DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=20.0, write=10.0, pool=5.0)
DIRECTIONS_PROFILE = "driving-hgv"
GEOCODE_PATH = "/geocode/search"
AUTOCOMPLETE_PATH = "/geocode/autocomplete"
DIRECTIONS_PATH = f"/v2/directions/{DIRECTIONS_PROFILE}/geojson"
# ORS answers 406 (error 2007) unless the directions request accepts GeoJSON.
GEOJSON_ACCEPT = "application/geo+json, application/json"
JSON_ACCEPT = "application/json"

# ORS directions error codes.
ORS_LIMIT_EXCEEDED_CODE = 2004
ORS_ROUTE_NOT_FOUND_CODES = frozenset({2009, 2010})
ORS_POINT_NOT_ROUTABLE_CODE = 2010
# ORS names the failing input point by index in its 2010 message; only this index is read.
_POINT_INDEX = re.compile(r"specified coordinate (\d+)")
# ORS answers 403 (or 429) with {"error": "Quota exceeded"} once the key's daily quota is used.
_QUOTA_EXCEEDED = re.compile(r"quota", re.IGNORECASE)

# Snapping radius (m) for the route's own endpoints (the ORS default) and for
# a generated via point, which may sit far from any road (-1 = unlimited).
ENDPOINT_RADIUS_METERS = 350
VIA_RADIUS_METERS = -1

# Successful geocoding answers are cached to spare the daily provider quota.
GEOCODE_CACHE_SECONDS = 24 * 60 * 60


@dataclass(frozen=True)
class GeocodeCandidate:
    label: str
    latitude: float
    longitude: float
    confidence: float


@dataclass(frozen=True)
class ProviderRoute:
    """One route as returned by ORS, normalized to miles, seconds and (lat, lng)."""

    provider_order: int
    distance_miles: float
    duration_seconds: float
    geometry: tuple[LatLng, ...]


class ProviderRequestRejected(Exception):
    """Internal: ORS answered with a 4xx that each endpoint maps to its own error."""

    def __init__(self, status_code: int, provider_code: int | None, point_index: int | None = None) -> None:
        super().__init__(f"status={status_code} provider_code={provider_code}")
        self.status_code = status_code
        self.provider_code = provider_code
        self.point_index = point_index


class ORSClient:
    """Thin OpenRouteService client. Pass `transport` to stub HTTP in tests."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        *,
        geocode_country: str = "",
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._geocode_country = geocode_country
        self._http = httpx.Client(base_url=base_url, timeout=DEFAULT_TIMEOUT, transport=transport)

    @classmethod
    def from_settings(cls) -> "ORSClient":
        return cls(
            api_key=settings.ORS_API_KEY,
            base_url=settings.ORS_BASE_URL,
            geocode_country=settings.ORS_GEOCODE_COUNTRY,
        )

    @property
    def geocode_country(self) -> str:
        """Country code geocoding is restricted to; empty means worldwide."""
        return self._geocode_country

    def close(self) -> None:
        self._http.close()

    def __repr__(self) -> str:
        return f"ORSClient(base_url={str(self._http.base_url)!r})"

    def geocode(self, text: str, size: int = 5) -> tuple[GeocodeCandidate, ...]:
        """Return up to `size` candidate places for free-text `text`, best first."""
        params: dict[str, Any] = {"text": text, "size": size}
        return self._cached_geocode(GEOCODE_PATH, "geocode", params)

    def autocomplete(self, text: str, limit: int = 5) -> tuple[GeocodeCandidate, ...]:
        """Place suggestions for partially typed `text` (ORS/Pelias autocomplete), best first."""
        params: dict[str, Any] = {"text": text}
        return self._cached_geocode(AUTOCOMPLETE_PATH, "autocomplete", params)[:limit]

    def _cached_geocode(
        self, path: str, endpoint: str, params: dict[str, Any]
    ) -> tuple[GeocodeCandidate, ...]:
        if self._geocode_country:
            params["boundary.country"] = self._geocode_country
        key = _geocode_cache_key(str(self._http.base_url), path, params)
        cached = cache.get(key)
        if cached is not None:
            return cached
        try:
            payload = self._request("GET", path, endpoint, JSON_ACCEPT, params=params)
        except ProviderRequestRejected:
            raise RoutingUnavailable("The geocoding provider rejected the request.") from None
        candidates = _parse_geocode(payload)
        cache.set(key, candidates, GEOCODE_CACHE_SECONDS)
        return candidates

    def directions(
        self, start: LatLng, end: LatLng, alternatives: int = 3, via: LatLng | None = None
    ) -> tuple[ProviderRoute, ...]:
        """Return up to `alternatives` truck routes from `start` to `end`, in provider order.

        With `via`, a single route forced through that point is requested
        (ORS does not combine alternatives with intermediate waypoints).
        Raises ProviderLimitExceeded when ORS rejects the request as over its
        limits (for alternatives this happens on trips longer than ~100 km).
        """
        points = [start, end] if via is None else [start, via, end]
        body: dict[str, Any] = {
            "coordinates": [[point[1], point[0]] for point in points],
            "instructions": False,
            "units": "m",
        }
        if via is not None:
            alternatives = 1
            body["radiuses"] = [ENDPOINT_RADIUS_METERS, VIA_RADIUS_METERS, ENDPOINT_RADIUS_METERS]
        if alternatives > 1:
            body["alternative_routes"] = {
                "target_count": alternatives,
                "share_factor": 0.6,
                "weight_factor": 1.4,
            }
        try:
            payload = self._request("POST", DIRECTIONS_PATH, "directions", GEOJSON_ACCEPT, json=body)
        except ProviderRequestRejected as rejected:
            if rejected.provider_code == ORS_LIMIT_EXCEEDED_CODE:
                raise ProviderLimitExceeded() from None
            if rejected.provider_code == ORS_POINT_NOT_ROUTABLE_CODE and rejected.point_index is not None:
                raise LocationNotRoutable(details={"point_index": rejected.point_index}) from None
            if rejected.provider_code in ORS_ROUTE_NOT_FOUND_CODES or rejected.status_code == 404:
                raise RouteNotFound() from None
            raise RoutingUnavailable("The routing provider rejected the request.") from None
        return _parse_directions(payload)[: max(alternatives, 1)]

    def _request(self, method: str, path: str, endpoint: str, accept: str, **kwargs: Any) -> Any:
        if not self._api_key:
            raise RoutingNotConfigured()
        headers = {"Authorization": self._api_key, "Accept": accept}
        try:
            response = self._http.request(method, path, headers=headers, **kwargs)
        except httpx.TimeoutException:
            logger.warning("ORS %s request timed out", endpoint)
            raise RoutingTimeout() from None
        except httpx.HTTPError as error:
            logger.warning("ORS %s request failed: %s", endpoint, type(error).__name__)
            raise RoutingUnavailable() from None

        if response.is_success:
            try:
                return response.json()
            except ValueError:
                logger.warning("ORS %s returned invalid JSON", endpoint)
                raise RoutingDataError() from None

        provider_code = _provider_error_code(response)
        logger.warning(
            "ORS %s request rejected: status=%s provider_code=%s",
            endpoint,
            response.status_code,
            provider_code,
        )
        if response.status_code in (403, 429) and _quota_exceeded(response):
            raise RoutingUnavailable(
                "The routing provider's daily request quota for this server has been used up. "
                "Please try again later (it resets at 00:00 UTC).",
                code="routing_quota_exceeded",
            )
        if response.status_code in (401, 403):
            raise RoutingUnavailable(
                "The routing provider rejected the server's credentials.",
                code="routing_auth_failed",
            )
        if response.status_code == 429:
            raise RoutingUnavailable(
                "The routing provider's rate limit was reached. Please try again shortly.",
                code="routing_rate_limited",
            )
        if response.is_server_error:
            raise RoutingUnavailable()
        raise ProviderRequestRejected(response.status_code, provider_code, _unroutable_point_index(response))


def _provider_error_code(response: httpx.Response) -> int | None:
    try:
        payload = response.json()
    except ValueError:
        return None
    error = payload.get("error") if isinstance(payload, dict) else None
    code = error.get("code") if isinstance(error, dict) else None
    return code if isinstance(code, int) and not isinstance(code, bool) else None


def _quota_exceeded(response: httpx.Response) -> bool:
    """True when ORS says the key's quota is used up (body: {"error": "Quota exceeded"})."""
    try:
        payload = response.json()
    except ValueError:
        return False
    error = payload.get("error") if isinstance(payload, dict) else None
    message = error.get("message") if isinstance(error, dict) else error
    return isinstance(message, str) and bool(_QUOTA_EXCEEDED.search(message))


def _geocode_cache_key(base_url: str, path: str, params: dict[str, Any]) -> str:
    # Hashed: the cache key must be short and free of spaces and control characters.
    raw = "|".join([base_url, path, *(f"{k}={params[k]}" for k in sorted(params))])
    return "ors-geocode:" + hashlib.sha256(raw.encode()).hexdigest()


def _unroutable_point_index(response: httpx.Response) -> int | None:
    """Index of the input coordinate ORS could not snap to a road (error 2010), if stated."""
    try:
        payload = response.json()
    except ValueError:
        return None
    error = payload.get("error") if isinstance(payload, dict) else None
    message = error.get("message") if isinstance(error, dict) else None
    match = _POINT_INDEX.search(message) if isinstance(message, str) else None
    return int(match.group(1)) if match else None


def _number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("not a finite number")
    return float(value)


def _lnglat_to_latlng(coordinate: Any) -> LatLng:
    if not isinstance(coordinate, (list, tuple)) or len(coordinate) < 2:
        raise ValueError("coordinate must be [lng, lat, ...]")
    return (_number(coordinate[1]), _number(coordinate[0]))


def _parse(payload: Any, parser: Callable[[Any], Any], what: str) -> Any:
    try:
        return parser(payload)
    except (KeyError, TypeError, ValueError, IndexError):
        logger.warning("ORS %s response had an unexpected shape", what)
        raise RoutingDataError() from None


def _parse_geocode(payload: Any) -> tuple[GeocodeCandidate, ...]:
    def parse(data: Any) -> tuple[GeocodeCandidate, ...]:
        candidates = []
        for feature in data["features"]:
            latitude, longitude = _lnglat_to_latlng(feature["geometry"]["coordinates"])
            properties = feature["properties"]
            label = properties["label"]
            if not isinstance(label, str) or not label.strip():
                raise ValueError("missing label")
            confidence = properties.get("confidence", 0)
            candidates.append(
                GeocodeCandidate(
                    label=label.strip(),
                    latitude=latitude,
                    longitude=longitude,
                    confidence=_number(confidence) if confidence is not None else 0.0,
                )
            )
        return tuple(candidates)

    return _parse(payload, parse, "geocode")


def _parse_directions(payload: Any) -> tuple[ProviderRoute, ...]:
    def parse(data: Any) -> tuple[ProviderRoute, ...]:
        features = data["features"]
        if not isinstance(features, list) or not features:
            raise ValueError("no routes")
        routes = []
        for order, feature in enumerate(features):
            summary = feature["properties"]["summary"]
            distance_meters = _number(summary["distance"])
            duration_seconds = _number(summary["duration"])
            if distance_meters <= 0 or duration_seconds <= 0:
                raise ValueError("route distance and duration must be positive")
            coordinates = feature["geometry"]["coordinates"]
            if not isinstance(coordinates, list):
                raise ValueError("coordinates must be a list")
            geometry = tuple(_lnglat_to_latlng(c) for c in coordinates)
            routes.append(
                ProviderRoute(
                    provider_order=order,
                    distance_miles=distance_meters / METERS_PER_MILE,
                    duration_seconds=duration_seconds,
                    geometry=geometry,
                )
            )
        return tuple(routes)

    routes = _parse(payload, parse, "directions")
    for route in routes:
        validate_geometry(route.geometry)
    return routes
