import math

import pytest

from routes.errors import RoutingDataError
from routes.geometry import (
    cumulative_distances,
    haversine_miles,
    interpolate_great_circle,
    offset_midpoint,
    point_at_distance,
    sample_polyline,
    validate_geometry,
)


def test_one_degree_of_latitude_is_about_69_miles():
    assert haversine_miles((30.0, -97.0), (31.0, -97.0)) == pytest.approx(69.0934, abs=1e-3)


def test_longitude_degree_shrinks_with_latitude():
    at_equator = haversine_miles((0.0, 0.0), (0.0, 1.0))
    at_sixty = haversine_miles((60.0, 0.0), (60.0, 1.0))
    assert at_sixty == pytest.approx(at_equator / 2, rel=1e-3)


def test_known_city_pair_distance():
    # Dallas to Houston great-circle distance is about 225 miles.
    assert haversine_miles((32.7767, -96.7970), (29.7604, -95.3698)) == pytest.approx(225, abs=2)


def test_cumulative_distances_accumulate_segment_lengths():
    points = [(0.0, 0.0), (0.0, 1.0), (0.0, 3.0)]
    one_degree = haversine_miles((0.0, 0.0), (0.0, 1.0))

    assert cumulative_distances(points) == pytest.approx((0.0, one_degree, 3 * one_degree))


def test_great_circle_midpoint_on_equator():
    assert interpolate_great_circle((0.0, 0.0), (0.0, 10.0), 0.5) == pytest.approx((0.0, 5.0))


def test_great_circle_interpolation_follows_curvature():
    # The great circle between two points at 60N bulges poleward of the parallel.
    lat, lng = interpolate_great_circle((60.0, -30.0), (60.0, 30.0), 0.5)
    assert lng == pytest.approx(0.0, abs=1e-9)
    assert lat > 60.0


@pytest.mark.parametrize(("fraction", "expected"), [(0, (10.0, 20.0)), (1, (11.0, 21.0))])
def test_interpolation_endpoints(fraction, expected):
    assert interpolate_great_circle((10.0, 20.0), (11.0, 21.0), fraction) == expected


def test_point_at_distance_uses_cumulative_distance_not_vertex_index():
    # Vertices at 30.0, 30.1 and 31.0: the middle vertex is near the start, so the
    # halfway point must be at ~30.5, not at the middle vertex.
    points = [(30.0, -97.0), (30.1, -97.0), (31.0, -97.0)]
    cumulative = cumulative_distances(points)

    lat, lng = point_at_distance(points, cumulative, cumulative[-1] / 2)

    assert lat == pytest.approx(30.5, abs=1e-6)
    assert lng == pytest.approx(-97.0)


def test_point_at_distance_at_vertex_and_clamped_ends():
    points = [(30.0, -97.0), (30.1, -97.0), (31.0, -97.0)]
    cumulative = cumulative_distances(points)

    assert point_at_distance(points, cumulative, cumulative[1]) == pytest.approx((30.1, -97.0))
    assert point_at_distance(points, cumulative, -5) == points[0]
    assert point_at_distance(points, cumulative, cumulative[-1] + 5) == points[-1]


def test_point_at_distance_skips_duplicate_vertices():
    points = [(30.0, -97.0), (30.5, -97.0), (30.5, -97.0), (31.0, -97.0)]
    cumulative = cumulative_distances(points)

    lat, _ = point_at_distance(points, cumulative, cumulative[-1] * 0.75)

    assert lat == pytest.approx(30.75, abs=1e-6)


@pytest.mark.parametrize(
    ("points", "message"),
    [
        ([], "fewer than two"),
        ([(30.0, -97.0)], "fewer than two"),
        ([(30.0, -97.0), (math.nan, -97.0)], "non-finite"),
        ([(30.0, -97.0), (30.0, math.inf)], "non-finite"),
        ([(30.0, -97.0), (91.0, -97.0)], "out-of-range"),
        ([(30.0, -97.0), (30.0, -181.0)], "out-of-range"),
        ([(30.0, -97.0), (30.0, -97.0)], "zero length"),
    ],
)
def test_validate_geometry_rejects_degenerate_input(points, message):
    with pytest.raises(RoutingDataError, match=message):
        validate_geometry(points)


def test_offset_midpoint_moves_left_for_positive_and_right_for_negative():
    south, north = (30.0, -97.0), (31.0, -97.0)
    left = offset_midpoint(south, north, 0.2)
    right = offset_midpoint(south, north, -0.2)

    # Travelling north, left is west (smaller longitude).
    assert left[1] < -97.0 < right[1]
    assert left[0] == pytest.approx(30.5, abs=1e-3)
    assert haversine_miles(left, (30.5, -97.0)) == pytest.approx(0.2 * haversine_miles(south, north), rel=0.01)


def test_offset_midpoint_without_offset_is_the_midpoint():
    assert offset_midpoint((30.0, -97.0), (31.0, -97.0), 0) == pytest.approx((30.5, -97.0))


def test_sample_polyline_spaces_points_evenly_and_keeps_ends():
    points = [(30.0, -97.0), (30.1, -97.0), (31.0, -97.0)]
    samples = sample_polyline(points, 5)

    assert samples[0] == points[0]
    assert samples[-1] == points[-1]
    assert [round(lat, 6) for lat, _ in samples] == [30.0, 30.25, 30.5, 30.75, 31.0]
