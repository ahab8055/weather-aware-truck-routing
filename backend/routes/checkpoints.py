"""Distance-based checkpoints along a route, with baseline ETAs.

Checkpoints sit at mile 0, every `interval` miles strictly before the
destination, and at the destination's exact distance.

ETA baseline: elapsed time is interpolated linearly by distance from the
route's total duration (constant average speed). It does not model stops,
breaks, traffic changes or speed differences between road types.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from routes.geometry import LatLng, cumulative_distances, point_at_distance, validate_geometry

ALLOWED_INTERVALS_MILES = (10, 25, 50)

# Interval points closer than this to the destination are dropped so the
# destination is not duplicated when the distance is an exact multiple.
DESTINATION_EPSILON_MILES = 1e-6


@dataclass(frozen=True)
class Checkpoint:
    """A sample point on a route: where it is and when the truck should get there."""

    index: int
    distance_miles: float
    latitude: float
    longitude: float
    elapsed_seconds: float
    eta: datetime


def checkpoint_distances(total_miles: float, interval_miles: int) -> tuple[float, ...]:
    """Distances (miles) for checkpoints: 0, each interval before the end, then the end."""
    if interval_miles not in ALLOWED_INTERVALS_MILES:
        raise ValueError(f"interval_miles must be one of {ALLOWED_INTERVALS_MILES}")
    if not math.isfinite(total_miles) or total_miles <= 0:
        raise ValueError(f"total_miles must be positive and finite, got {total_miles}")
    distances = [0.0]
    step = 1
    while total_miles - step * interval_miles > DESTINATION_EPSILON_MILES:
        distances.append(float(step * interval_miles))
        step += 1
    distances.append(total_miles)
    return tuple(distances)


def generate_checkpoints(
    geometry: Sequence[LatLng],
    distance_miles: float,
    duration_seconds: float,
    departure_time: datetime,
    interval_miles: int,
) -> tuple[Checkpoint, ...]:
    """Place checkpoints along `geometry` and estimate their arrival times.

    `distance_miles` is the provider's route distance. The polyline's own
    great-circle length differs slightly, so each checkpoint is placed at the
    same fraction of the polyline length as of the route distance.
    """
    if departure_time.tzinfo is None or departure_time.utcoffset() is None:
        raise ValueError("departure_time must be timezone-aware")
    if not math.isfinite(duration_seconds) or duration_seconds <= 0:
        raise ValueError(f"duration_seconds must be positive and finite, got {duration_seconds}")
    points = validate_geometry(geometry)
    cumulative = cumulative_distances(points)
    geometry_miles = cumulative[-1]

    checkpoints = []
    for index, distance in enumerate(checkpoint_distances(distance_miles, interval_miles)):
        progress = distance / distance_miles
        latitude, longitude = point_at_distance(points, cumulative, progress * geometry_miles)
        elapsed_seconds = progress * duration_seconds
        checkpoints.append(
            Checkpoint(
                index=index,
                distance_miles=distance,
                latitude=latitude,
                longitude=longitude,
                elapsed_seconds=elapsed_seconds,
                eta=departure_time + timedelta(seconds=elapsed_seconds),
            )
        )
    return tuple(checkpoints)
