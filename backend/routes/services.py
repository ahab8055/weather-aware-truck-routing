"""Route-candidate planning: geocode both ends, fetch alternatives, add checkpoints."""

import logging
import math
from dataclasses import dataclass, replace
from datetime import datetime

from routes.checkpoints import Checkpoint, generate_checkpoints
from routes.errors import (
    LocationNotRoutable,
    ProviderLimitExceeded,
    RouteNotFound,
    RouteTooLong,
    RoutingDataError,
    RoutingError,
    SameLocation,
)
from routes.geocoding import ResolvedLocation, resolve_location
from routes.geometry import LatLng, haversine_miles, offset_midpoint, sample_polyline
from routes.ors import ORSClient, ProviderRoute

logger = logging.getLogger(__name__)

REQUESTED_ROUTE_COUNT = 3
# Endpoints closer than this are treated as the same place.
SAME_LOCATION_MILES = 0.1

# ORS only calculates alternative routes for trips up to ~100 km. For longer
# trips, alternatives are requested through a via point: the midpoint of the
# straight origin-destination line pushed sideways by these fractions of the
# straight-line distance (alternating sides), until enough distinct routes exist.
DETOUR_OFFSETS = (0.15, -0.15, 0.3, -0.3)
# A detour longer than this multiple of the best route's distance is not offered.
MAX_DETOUR_RATIO = 1.5
# A detour is a duplicate when this share of it lies within OVERLAP_MILES of an
# already accepted route.
MAX_OVERLAP_SHARE = 0.8
OVERLAP_MILES = 1.0
# Sampling density for the overlap test: the detour is sampled at a fixed
# count, the accepted route roughly every OVERLAP_MILES / 2.
DETOUR_SAMPLE_COUNT = 100
MAX_REFERENCE_SAMPLES = 2000

ALTERNATIVES_VIA_NOTE = (
    "OpenRouteService only calculates alternative routes for trips up to about "
    "100 km (62 miles), so the alternatives were found by routing through points "
    "on either side of the direct line."
)
ALTERNATIVES_LIMIT_NOTE = (
    "OpenRouteService only calculates alternative routes for trips up to about "
    "100 km (62 miles), and no distinct detour route was found; showing the single best route."
)


@dataclass(frozen=True)
class RouteRequest:
    origin: str
    destination: str
    departure_time: datetime
    checkpoint_interval_miles: int
    load_weight_lbs: float


@dataclass(frozen=True)
class RouteCandidate:
    """One provider route with its checkpoints and the request context it belongs to."""

    id: str
    provider_order: int
    distance_miles: float
    duration_seconds: float
    geometry: tuple[LatLng, ...]
    checkpoints: tuple[Checkpoint, ...]
    origin: ResolvedLocation
    destination: ResolvedLocation
    departure_time: datetime
    checkpoint_interval_miles: int
    load_weight_lbs: float


@dataclass(frozen=True)
class RouteCandidates:
    origin: ResolvedLocation
    destination: ResolvedLocation
    departure_time: datetime
    checkpoint_interval_miles: int
    load_weight_lbs: float
    requested_route_count: int
    routes: tuple[RouteCandidate, ...]
    alternatives_note: str | None


def _fetch_routes(
    client: ORSClient, origin: LatLng, destination: LatLng
) -> tuple[tuple[ProviderRoute, ...], str | None]:
    try:
        return client.directions(origin, destination, alternatives=REQUESTED_ROUTE_COUNT), None
    except ProviderLimitExceeded:
        pass
    try:
        best = client.directions(origin, destination, alternatives=1)
    except ProviderLimitExceeded:
        raise RouteTooLong() from None
    routes = _with_detour_alternatives(client, origin, destination, best[0])
    if len(routes) == 1:
        return routes, ALTERNATIVES_LIMIT_NOTE
    if len(routes) < REQUESTED_ROUTE_COUNT:
        return routes, f"{ALTERNATIVES_VIA_NOTE} Only {len(routes)} distinct routes were found."
    return routes, ALTERNATIVES_VIA_NOTE


def _overlap_share(route: ProviderRoute, reference: tuple[LatLng, ...]) -> float:
    """Share of `route` lying within OVERLAP_MILES of the sampled `reference` route."""
    samples = sample_polyline(route.geometry, DETOUR_SAMPLE_COUNT)
    near = sum(
        1 for point in samples if any(haversine_miles(point, r) <= OVERLAP_MILES for r in reference)
    )
    return near / len(samples)


def _reference_samples(route: ProviderRoute) -> tuple[LatLng, ...]:
    count = math.ceil(route.distance_miles / (OVERLAP_MILES / 2)) + 1
    return sample_polyline(route.geometry, min(max(count, 2), MAX_REFERENCE_SAMPLES))


def _with_detour_alternatives(
    client: ORSClient, origin: LatLng, destination: LatLng, best: ProviderRoute
) -> tuple[ProviderRoute, ...]:
    """`best` plus up to two distinct, not-too-long routes forced through offset via points.

    A detour the provider cannot route is skipped; any other provider failure
    (rate limit, quota, timeout) stops the search and keeps what was found.
    """
    routes = [best]
    references = [_reference_samples(best)]
    for offset in DETOUR_OFFSETS:
        if len(routes) >= REQUESTED_ROUTE_COUNT:
            break
        via = offset_midpoint(origin, destination, offset)
        try:
            (detour,) = client.directions(origin, destination, via=via)
        except (RouteNotFound, ProviderLimitExceeded, RoutingDataError) as error:
            logger.info("Detour route via offset %s skipped: %s", offset, error.code)
            continue
        except RoutingError as error:
            logger.warning("Detour route search stopped: %s", error.code)
            break
        if detour.distance_miles > MAX_DETOUR_RATIO * best.distance_miles:
            continue
        if any(_overlap_share(detour, ref) >= MAX_OVERLAP_SHARE for ref in references):
            continue
        routes.append(replace(detour, provider_order=len(routes)))
        references.append(_reference_samples(detour))
    return tuple(routes)


def _not_routable(
    error: LocationNotRoutable, origin: ResolvedLocation, destination: ResolvedLocation
) -> RouteNotFound:
    """Name the endpoint the provider could not reach, so the user knows which field to change."""
    ends = {0: ("origin", origin), 1: ("destination", destination)}
    end = ends.get(error.details.get("point_index"))
    if end is None:
        return RouteNotFound()
    field, location = end
    return LocationNotRoutable(
        f'The {field} "{location.query}" is not near a road trucks can use. Large areas such as '
        "counties are placed at their centre point, which can fall in a park, forest or water. "
        "Try a city, street address or landmark instead.",
        details={"query": location.query, "field": field},
    )


def plan_route_candidates(client: ORSClient, request: RouteRequest) -> RouteCandidates:
    """Resolve endpoints, fetch up to three provider routes and generate checkpoints.

    Only routes actually returned by the provider are included, in provider order.
    Load weight is carried through; it does not affect routing yet.
    """
    origin = resolve_location(client, request.origin)
    destination = resolve_location(client, request.destination)
    if haversine_miles(origin.coordinates, destination.coordinates) < SAME_LOCATION_MILES:
        raise SameLocation(
            f'Origin "{origin.label}" and destination "{destination.label}" '
            "resolve to the same place."
        )

    try:
        provider_routes, note = _fetch_routes(client, origin.coordinates, destination.coordinates)
    except LocationNotRoutable as error:
        raise _not_routable(error, origin, destination) from None
    routes = tuple(
        RouteCandidate(
            id=f"route-{route.provider_order + 1}",
            provider_order=route.provider_order,
            distance_miles=route.distance_miles,
            duration_seconds=route.duration_seconds,
            geometry=route.geometry,
            checkpoints=generate_checkpoints(
                route.geometry,
                route.distance_miles,
                route.duration_seconds,
                request.departure_time,
                request.checkpoint_interval_miles,
            ),
            origin=origin,
            destination=destination,
            departure_time=request.departure_time,
            checkpoint_interval_miles=request.checkpoint_interval_miles,
            load_weight_lbs=request.load_weight_lbs,
        )
        for route in provider_routes
    )
    return RouteCandidates(
        origin=origin,
        destination=destination,
        departure_time=request.departure_time,
        checkpoint_interval_miles=request.checkpoint_interval_miles,
        load_weight_lbs=request.load_weight_lbs,
        requested_route_count=REQUESTED_ROUTE_COUNT,
        routes=routes,
        alternatives_note=note,
    )
