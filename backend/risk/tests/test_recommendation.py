import pytest

from risk.recommendation import NO_SAFE_ROUTE_MESSAGE, recommend_route
from risk.summary import RouteRiskSummary


def route(route_id, severe=0.0, high=0.0, average=0.5, duration=3_600, no_travel=False):
    return RouteRiskSummary(
        route_id=route_id,
        total_distance_miles=200,
        duration_seconds=duration,
        severe_miles=severe,
        high_miles=high,
        no_travel_miles=10.0 if no_travel else 0.0,
        average_risk_score=None if no_travel else average,
        has_no_travel=no_travel,
        segments=(),
    )


def ranked_ids(result):
    return [ranked.summary.route_id for ranked in result.ranked_safe_routes]


def test_fewer_severe_miles_wins_despite_much_longer_duration():
    fast = route("fast", severe=5, high=0, average=0.4, duration=3 * 3_600)
    slow = route("slow", severe=0, high=60, average=1.8, duration=6 * 3_600)

    result = recommend_route([fast, slow])

    assert result.recommended is slow
    assert ranked_ids(result) == ["slow", "fast"]
    assert [r.rank for r in result.ranked_safe_routes] == [1, 2]


def test_high_miles_break_severe_tie():
    a = route("a", severe=10, high=30, average=0.9, duration=3_000)
    b = route("b", severe=10, high=12, average=1.5, duration=9_000)

    assert recommend_route([a, b]).recommended is b


def test_average_risk_breaks_severe_and_high_tie():
    a = route("a", severe=10, high=12, average=1.25, duration=3_000)
    b = route("b", severe=10, high=12, average=1.1, duration=9_000)

    assert recommend_route([a, b]).recommended is b


def test_duration_breaks_tie_on_first_three_criteria():
    a = route("a", severe=10, high=12, average=1.1, duration=9_000)
    b = route("b", severe=10, high=12, average=1.1, duration=8_999)

    assert recommend_route([a, b]).recommended is b


def test_float_noise_within_rounding_is_a_tie_and_falls_through_to_duration():
    a = route("a", severe=10.000000001, high=5, average=1.0000001, duration=7_000)
    b = route("b", severe=10.0, high=5.000000001, average=1.0, duration=7_100)

    assert ranked_ids(recommend_route([a, b])) == ["a", "b"]


def test_unsafe_routes_are_excluded_even_if_otherwise_best():
    unsafe = route("unsafe", severe=0, high=0, duration=1_000, no_travel=True)
    safe = route("safe", severe=25, high=40, average=2.2, duration=9_000)

    result = recommend_route([unsafe, safe])

    assert result.recommended is safe
    assert ranked_ids(result) == ["safe"]
    assert result.unsafe_routes == (unsafe,)
    assert result.safe_route_available
    assert result.message == "Recommended route: safe."


def test_no_safe_recommendation_when_all_routes_unsafe():
    routes = [route("a", no_travel=True), route("b", no_travel=True)]

    result = recommend_route(routes)

    assert result.recommended is None
    assert not result.safe_route_available
    assert result.ranked_safe_routes == ()
    assert [r.route_id for r in result.unsafe_routes] == ["a", "b"]
    assert result.message == NO_SAFE_ROUTE_MESSAGE


def test_exact_ties_keep_input_order():
    a = route("a", severe=3, high=4, average=1.2, duration=5_000)
    b = route("b", severe=3, high=4, average=1.2, duration=5_000)

    assert ranked_ids(recommend_route([a, b])) == ["a", "b"]
    assert ranked_ids(recommend_route([b, a])) == ["b", "a"]


def test_three_routes_fully_ordered():
    routes = [
        route("c", severe=0, high=20, average=1.0, duration=4_000),
        route("a", severe=0, high=10, average=1.5, duration=6_000),
        route("b", severe=0, high=10, average=1.5, duration=5_000),
    ]

    assert ranked_ids(recommend_route(routes)) == ["b", "a", "c"]


def test_rejects_empty_candidates():
    with pytest.raises(ValueError, match="At least one"):
        recommend_route([])


def test_rejects_duplicate_route_ids():
    with pytest.raises(ValueError, match="unique"):
        recommend_route([route("a"), route("a")])
