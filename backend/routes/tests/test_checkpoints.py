from datetime import datetime, timedelta, timezone

import pytest

from risk.engine import WeatherConditions, assess_checkpoint
from risk.summary import RouteCheckpoint, summarize_route
from routes.checkpoints import checkpoint_distances, generate_checkpoints

CENTRAL = timezone(timedelta(hours=-5))
DEPARTURE = datetime(2026, 10, 19, 8, 0, tzinfo=CENTRAL)
MERIDIAN = [(30.0, -97.0), (30.1, -97.0), (30.7, -97.0), (31.0, -97.0)]
MERIDIAN_MILES = 69.0934


@pytest.mark.parametrize(
    ("total", "interval", "expected"),
    [
        (120.4, 10, (0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120, 120.4)),
        (120.4, 25, (0, 25, 50, 75, 100, 120.4)),
        (120.4, 50, (0, 50, 100, 120.4)),
    ],
)
def test_checkpoint_distances_for_each_allowed_interval(total, interval, expected):
    assert checkpoint_distances(total, interval) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("total", "interval", "expected"),
    [
        (50.0, 25, (0, 25, 50)),
        (100.0, 10, (0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100)),
        (50.0, 50, (0, 50)),
        (50.0000000001, 25, (0, 25, 50.0000000001)),
    ],
)
def test_exact_multiples_do_not_duplicate_destination(total, interval, expected):
    distances = checkpoint_distances(total, interval)

    assert distances == pytest.approx(expected)
    assert len(set(distances)) == len(distances)


@pytest.mark.parametrize("interval", [10, 25, 50])
def test_route_shorter_than_interval_has_origin_and_destination_only(interval):
    assert checkpoint_distances(7.25, interval) == (0.0, 7.25)


@pytest.mark.parametrize("interval", [0, 5, 15, 100])
def test_rejects_unsupported_interval(interval):
    with pytest.raises(ValueError, match="interval"):
        checkpoint_distances(100, interval)


@pytest.mark.parametrize("total", [0, -1, float("nan"), float("inf")])
def test_rejects_invalid_total(total):
    with pytest.raises(ValueError, match="total_miles"):
        checkpoint_distances(total, 10)


def test_generate_checkpoints_positions_etas_and_endpoints():
    duration = 3_600.0
    checkpoints = generate_checkpoints(MERIDIAN, MERIDIAN_MILES, duration, DEPARTURE, 25)

    assert [c.index for c in checkpoints] == [0, 1, 2, 3]
    assert [c.distance_miles for c in checkpoints] == pytest.approx([0, 25, 50, MERIDIAN_MILES])

    first, at_25, at_50, last = checkpoints
    assert (first.latitude, first.longitude) == (30.0, -97.0)
    assert (last.latitude, last.longitude) == (31.0, -97.0)
    # 25 of ~69.09 miles north along the meridian, between vertices 30.1 and 30.7.
    assert at_25.latitude == pytest.approx(30.0 + 25 / MERIDIAN_MILES, abs=1e-4)
    assert at_25.longitude == pytest.approx(-97.0)
    assert at_50.latitude == pytest.approx(30.0 + 50 / MERIDIAN_MILES, abs=1e-4)

    assert first.elapsed_seconds == 0
    assert first.eta == DEPARTURE
    assert at_25.elapsed_seconds == pytest.approx(duration * 25 / MERIDIAN_MILES)
    assert last.elapsed_seconds == pytest.approx(duration)
    assert last.eta == DEPARTURE + timedelta(hours=1)
    assert last.eta.utcoffset() == timedelta(hours=-5)


def test_checkpoint_position_scales_when_provider_distance_differs_from_geometry():
    # Provider says 80 miles over a ~69.09-mile polyline: the halfway checkpoint
    # (40 of 80 miles) must land halfway along the polyline.
    checkpoints = generate_checkpoints(MERIDIAN, 80.0, 4_000, DEPARTURE, 10)

    halfway = next(c for c in checkpoints if c.distance_miles == 40)
    assert halfway.latitude == pytest.approx(30.5, abs=1e-6)
    assert halfway.elapsed_seconds == pytest.approx(2_000)


def test_rejects_naive_departure_time():
    with pytest.raises(ValueError, match="timezone"):
        generate_checkpoints(MERIDIAN, MERIDIAN_MILES, 3_600, datetime(2026, 10, 19, 8), 25)


@pytest.mark.parametrize("duration", [0, -10, float("nan")])
def test_rejects_invalid_duration(duration):
    with pytest.raises(ValueError, match="duration"):
        generate_checkpoints(MERIDIAN, MERIDIAN_MILES, duration, DEPARTURE, 25)


@pytest.mark.parametrize("interval", [10, 25, 50])
def test_checkpoints_are_accepted_by_risk_summary(interval):
    checkpoints = generate_checkpoints(MERIDIAN, MERIDIAN_MILES, 3_600, DEPARTURE, interval)
    calm = assess_checkpoint(WeatherConditions(5, 0, 0), 30_000)

    summary = summarize_route(
        "route-1",
        [RouteCheckpoint(distance_miles=c.distance_miles, risk=calm) for c in checkpoints],
        MERIDIAN_MILES,
        3_600,
    )

    assert summary.is_safe
    assert summary.average_risk_score == 0
