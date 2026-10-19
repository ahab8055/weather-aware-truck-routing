import math

import pytest

from risk.engine import CheckpointRisk, LoadRestriction
from risk.levels import RiskLevel
from risk.summary import RouteCheckpoint, summarize_route

LOW, MODERATE, HIGH, SEVERE, NO_TRAVEL = RiskLevel


def checkpoint(distance_miles, level):
    risk = CheckpointRisk(
        wind=level,
        rain=LOW,
        snow=LOW,
        base=level,
        overall=level,
        load_restriction=LoadRestriction.NONE,
    )
    return RouteCheckpoint(distance_miles=distance_miles, risk=risk)


def test_single_segment_route():
    summary = summarize_route(
        "r1", [checkpoint(0, HIGH), checkpoint(25, HIGH)], 25, 1_800
    )

    assert [s.length_miles for s in summary.segments] == [12.5, 12.5]
    assert summary.high_miles == 25
    assert summary.severe_miles == 0
    assert summary.average_risk_score == 2
    assert summary.is_safe


def test_unequal_gaps_mixed_levels_are_distance_weighted():
    # Midpoints at 5, 25 and 45 give segments of 5, 20, 20 and 5 miles.
    checkpoints = [
        checkpoint(0, LOW),
        checkpoint(10, HIGH),
        checkpoint(40, SEVERE),
        checkpoint(50, MODERATE),
    ]

    summary = summarize_route("r1", checkpoints, 50, 3_600)

    assert [(s.start_miles, s.end_miles, s.level) for s in summary.segments] == [
        (0, 5, LOW),
        (5, 25, HIGH),
        (25, 45, SEVERE),
        (45, 50, MODERATE),
    ]
    assert summary.severe_miles == 20
    assert summary.high_miles == 20
    assert summary.no_travel_miles == 0
    # (0*5 + 2*20 + 3*20 + 1*5) / 50
    assert summary.average_risk_score == pytest.approx(2.1)
    assert summary.total_distance_miles == 50
    assert summary.duration_seconds == 3_600


def test_average_differs_from_checkpoint_count_average():
    # Two of three checkpoints are LOW, but the SEVERE one represents most miles.
    checkpoints = [checkpoint(0, LOW), checkpoint(2, LOW), checkpoint(100, SEVERE)]

    summary = summarize_route("r1", checkpoints, 100, 6_000)

    assert summary.severe_miles == 49
    assert summary.average_risk_score == pytest.approx(3 * 49 / 100)


def test_no_travel_segment_marks_route_unsafe():
    checkpoints = [
        checkpoint(0, LOW),
        checkpoint(20, NO_TRAVEL),
        checkpoint(40, SEVERE),
        checkpoint(60, LOW),
    ]

    summary = summarize_route("r1", checkpoints, 60, 4_000)

    assert summary.has_no_travel
    assert not summary.is_safe
    assert summary.no_travel_miles == 20
    assert summary.severe_miles == 20
    assert summary.average_risk_score is None


def test_last_checkpoint_within_tolerance_of_route_distance():
    summary = summarize_route("r1", [checkpoint(0, LOW), checkpoint(99.995, LOW)], 100, 60)

    assert summary.total_distance_miles == 100
    assert math.fsum(s.length_miles for s in summary.segments) == pytest.approx(99.995)


def test_segment_lengths_sum_to_distance_with_many_fractional_steps():
    distances = [i * 0.1 for i in range(1001)]
    levels = [LOW, MODERATE, HIGH, SEVERE]
    checkpoints = [checkpoint(d, levels[i % 4]) for i, d in enumerate(distances)]

    summary = summarize_route("r1", checkpoints, 100, 7_200)

    total = math.fsum(s.length_miles for s in summary.segments)
    assert total == pytest.approx(100, rel=1e-12)
    for previous, current in zip(summary.segments, summary.segments[1:]):
        assert previous.end_miles == current.start_miles
    by_level = summary.severe_miles + summary.high_miles
    assert by_level == pytest.approx(50, abs=0.1)


@pytest.mark.parametrize("bad_value", [0, -10, math.nan, math.inf])
def test_rejects_invalid_total_distance(bad_value):
    with pytest.raises(ValueError, match="total_distance_miles"):
        summarize_route("r1", [checkpoint(0, LOW), checkpoint(10, LOW)], bad_value, 600)


@pytest.mark.parametrize("bad_value", [0, -1, math.nan, math.inf])
def test_rejects_invalid_duration(bad_value):
    with pytest.raises(ValueError, match="duration_seconds"):
        summarize_route("r1", [checkpoint(0, LOW), checkpoint(10, LOW)], 10, bad_value)


@pytest.mark.parametrize(
    ("distances", "message"),
    [
        ([0], "two checkpoints"),
        ([], "two checkpoints"),
        ([0, 5, 5, 10], "strictly increasing"),
        ([0, 6, 4, 10], "strictly increasing"),
        ([1, 10], "origin"),
        ([0, 9], "route distance"),
        ([0, math.nan, 10], "finite"),
    ],
)
def test_rejects_invalid_checkpoints(distances, message):
    with pytest.raises(ValueError, match=message):
        summarize_route("r1", [checkpoint(d, LOW) for d in distances], 10, 600)
