"""Spherical geometry helpers for route polylines.

Points are (latitude, longitude) tuples in degrees, the order Leaflet expects.
"""

import math
from bisect import bisect_right
from collections.abc import Sequence

from routes.errors import RoutingDataError

EARTH_RADIUS_MILES = 3958.7613
MILES_PER_DEGREE_LATITUDE = EARTH_RADIUS_MILES * math.pi / 180

LatLng = tuple[float, float]


def haversine_miles(a: LatLng, b: LatLng) -> float:
    """Great-circle distance between two points in miles."""
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_MILES * math.asin(min(1.0, math.sqrt(h)))


def cumulative_distances(points: Sequence[LatLng]) -> tuple[float, ...]:
    """Distance in miles from the first point to each point along the polyline."""
    totals = [0.0]
    for previous, current in zip(points, points[1:]):
        totals.append(totals[-1] + haversine_miles(previous, current))
    return tuple(totals)


def interpolate_great_circle(a: LatLng, b: LatLng, fraction: float) -> LatLng:
    """Point at `fraction` (0..1) of the way from `a` to `b` along the great circle."""
    if fraction <= 0:
        return a
    if fraction >= 1:
        return b
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    delta = haversine_miles(a, b) / EARTH_RADIUS_MILES
    if delta < 1e-12:
        return a
    sin_delta = math.sin(delta)
    weight_a = math.sin((1 - fraction) * delta) / sin_delta
    weight_b = math.sin(fraction * delta) / sin_delta
    x = weight_a * math.cos(lat1) * math.cos(lon1) + weight_b * math.cos(lat2) * math.cos(lon2)
    y = weight_a * math.cos(lat1) * math.sin(lon1) + weight_b * math.cos(lat2) * math.sin(lon2)
    z = weight_a * math.sin(lat1) + weight_b * math.sin(lat2)
    return (
        math.degrees(math.atan2(z, math.hypot(x, y))),
        math.degrees(math.atan2(y, x)),
    )


def offset_midpoint(a: LatLng, b: LatLng, fraction: float) -> LatLng:
    """Midpoint of `a`-`b` moved sideways by `fraction` of their distance.

    Positive fractions move left of the direction of travel, negative ones
    right. Uses a local flat-earth approximation, which is accurate enough for
    placing a routing via point.
    """
    mid_lat, mid_lng = interpolate_great_circle(a, b, 0.5)
    cos_lat = max(math.cos(math.radians(mid_lat)), 1e-6)
    east = (b[1] - a[1]) * MILES_PER_DEGREE_LATITUDE * cos_lat
    north = (b[0] - a[0]) * MILES_PER_DEGREE_LATITUDE
    length = math.hypot(east, north)
    if length == 0:
        return (mid_lat, mid_lng)
    shift = fraction * haversine_miles(a, b)
    latitude = mid_lat + (east / length * shift) / MILES_PER_DEGREE_LATITUDE
    longitude = mid_lng + (-north / length * shift) / (MILES_PER_DEGREE_LATITUDE * cos_lat)
    return (max(-90.0, min(90.0, latitude)), (longitude + 180) % 360 - 180)


def sample_polyline(points: Sequence[LatLng], count: int) -> tuple[LatLng, ...]:
    """`count` (>= 2) points spaced evenly by distance along the polyline, ends included."""
    cumulative = cumulative_distances(points)
    total = cumulative[-1]
    return tuple(point_at_distance(points, cumulative, total * i / (count - 1)) for i in range(count))


def point_at_distance(
    points: Sequence[LatLng], cumulative: Sequence[float], target_miles: float
) -> LatLng:
    """Point `target_miles` along the polyline, interpolated within its segment.

    `cumulative` must come from `cumulative_distances(points)`. Targets outside
    the polyline are clamped to its endpoints.
    """
    if target_miles <= 0:
        return points[0]
    if target_miles >= cumulative[-1]:
        return points[-1]
    index = min(bisect_right(cumulative, target_miles) - 1, len(points) - 2)
    segment_length = cumulative[index + 1] - cumulative[index]
    if segment_length <= 0:
        return points[index]
    fraction = (target_miles - cumulative[index]) / segment_length
    return interpolate_great_circle(points[index], points[index + 1], fraction)


def validate_geometry(points: Sequence[LatLng]) -> tuple[LatLng, ...]:
    """Return the polyline as a tuple, or raise RoutingDataError if it is unusable."""
    if len(points) < 2:
        raise RoutingDataError("The route geometry has fewer than two points.")
    for latitude, longitude in points:
        if not (math.isfinite(latitude) and math.isfinite(longitude)):
            raise RoutingDataError("The route geometry contains non-finite coordinates.")
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise RoutingDataError("The route geometry contains out-of-range coordinates.")
    if cumulative_distances(points)[-1] <= 0:
        raise RoutingDataError("The route geometry has zero length.")
    return tuple(points)
