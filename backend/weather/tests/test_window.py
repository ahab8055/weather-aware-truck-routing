from datetime import UTC, datetime, timedelta, timezone

import pytest

from risk.engine import LoadRestriction
from risk.levels import RiskLevel
from weather.errors import weather_unavailable
from weather.forecast import MISSING_VALUES, OUTSIDE_COVERAGE, NormalizedWeather, WeatherUnavailable
from weather.open_meteo import HourlySeries
from weather.window import FORECAST_WINDOW_HOURS, forecast_window_for_locations, window_targets

CENTRAL = timezone(timedelta(hours=-5))
NOW = datetime(2026, 10, 19, 12, tzinfo=UTC)
DEPARTURE = datetime(2026, 10, 20, 8, 0, tzinfo=CENTRAL)  # 13:00 UTC


class FakeSource:
    """`conditions(lat, lng, hour)` -> (wind mph, rain in, snow in), values may be None."""

    def __init__(self, conditions=lambda lat, lng, t: (8.0, 0.0, 0.0), error=None):
        self.conditions = conditions
        self.error = error
        self.calls = []

    def fetch_hourly(self, locations, start, end):
        self.calls.append((list(locations), start, end))
        if self.error:
            return [self.error] * len(locations)
        times = []
        moment = start
        while moment <= end:
            times.append(moment)
            moment += timedelta(hours=1)
        results = []
        for lat, lng in locations:
            wind, rain, snow = (tuple(c) for c in zip(*(self.conditions(lat, lng, t) for t in times)))
            results.append(HourlySeries(tuple(times), wind, rain, snow))
        return results


def test_window_has_49_hourly_slots_from_departure():
    targets = window_targets(DEPARTURE)

    assert len(targets) == FORECAST_WINDOW_HOURS + 1 == 49
    assert targets[0] == DEPARTURE
    assert targets[-1] == DEPARTURE + timedelta(hours=48)
    assert all(b - a == timedelta(hours=1) for a, b in zip(targets, targets[1:]))


def test_naive_departure_is_rejected():
    with pytest.raises(ValueError):
        window_targets(datetime(2026, 10, 20, 8))


def test_each_slot_uses_its_own_forecast_hour():
    def wind_by_hour(lat, lng, t):
        return (float(t.hour), 0.0, 0.0)

    result = forecast_window_for_locations(FakeSource(wind_by_hour), [(30.0, -97.0)], DEPARTURE, 20_000, now=NOW)

    observations = result.locations[0].observations
    assert observations[0].weather.forecast_time == datetime(2026, 10, 20, 13, tzinfo=UTC)
    assert observations[0].weather.wind_speed_mph == 13.0
    assert observations[6].weather.forecast_time == datetime(2026, 10, 20, 19, tzinfo=UTC)
    assert observations[6].weather.wind_speed_mph == 19.0
    assert result.slots[6].offset_hours == 6
    assert result.slots[6].target_time == DEPARTURE + timedelta(hours=6)
    assert result.slots[6].forecast_time == datetime(2026, 10, 20, 19, tzinfo=UTC)
    assert result.coverage_note is None


@pytest.mark.parametrize(
    ("minute", "expected_first_hour"),
    [(10, 13), (29, 13), (30, 14), (50, 14)],
)
def test_off_hour_departure_maps_slots_to_nearest_hour(minute, expected_first_hour):
    departure = datetime(2026, 10, 20, 8, minute, tzinfo=CENTRAL)

    result = forecast_window_for_locations(FakeSource(), [(30.0, -97.0)], departure, 20_000, now=NOW)

    first = result.locations[0].observations[0].weather
    assert first.forecast_time == datetime(2026, 10, 20, expected_first_hour, tzinfo=UTC)
    assert abs(first.forecast_time - departure) <= timedelta(minutes=30)


def test_nearby_and_duplicate_locations_share_one_fetch_and_keep_input_order():
    source = FakeSource(lambda lat, lng, t: (lat, 0.0, 0.0))
    locations = [(30.0, -97.0), (31.0, -97.0), (30.001, -97.001), (30.0, -97.0)]

    result = forecast_window_for_locations(source, locations, DEPARTURE, 20_000, now=NOW)

    assert len(source.calls) == 1
    fetched, start, end = source.calls[0]
    assert fetched == [(30.0, -97.0), (31.0, -97.0)]
    assert (start, end) == (datetime(2026, 10, 20, 13, tzinfo=UTC), datetime(2026, 10, 22, 13, tzinfo=UTC))
    assert [(loc.latitude, loc.longitude) for loc in result.locations] == locations
    assert [loc.observations[0].weather.wind_speed_mph for loc in result.locations] == [30.0, 31.0, 30.0, 30.0]


def test_units_pass_through_and_risk_uses_engine_with_load_rule():
    def storm_after_noon(lat, lng, t):
        return (47.0, 0.3, 2.5) if t >= datetime(2026, 10, 20, 18, tzinfo=UTC) else (8.0, 0.0, 0.0)

    result = forecast_window_for_locations(FakeSource(storm_after_noon), [(30.0, -97.0)], DEPARTURE, 35_000, now=NOW)

    calm, stormy = result.locations[0].observations[0], result.locations[0].observations[5]
    assert calm.risk.overall is RiskLevel.LOW
    assert stormy.weather == NormalizedWeather(datetime(2026, 10, 20, 18, tzinfo=UTC), 47.0, 0.3, 2.5)
    assert (stormy.risk.wind, stormy.risk.rain, stormy.risk.snow) == (
        RiskLevel.SEVERE,
        RiskLevel.HIGH,
        RiskLevel.SEVERE,
    )
    assert stormy.risk.overall is RiskLevel.NO_TRAVEL
    assert stormy.risk.load_restriction is LoadRestriction.HEAVY_LOAD_WIND_NO_TRAVEL


def test_missing_values_are_unavailable_never_low():
    def gap(lat, lng, t):
        return (None, 0.0, 0.0) if t.hour == 15 else (8.0, 0.0, 0.0)

    result = forecast_window_for_locations(FakeSource(gap), [(30.0, -97.0)], DEPARTURE, 20_000, now=NOW)

    missing = result.locations[0].observations[2]
    assert isinstance(missing.weather, WeatherUnavailable)
    assert missing.weather.reason == MISSING_VALUES
    assert missing.risk is None
    assert result.slots[2].forecast_time is None


def test_window_crossing_forecast_horizon_marks_tail_outside_coverage():
    # Forecasts end 2026-11-03 23:00 UTC for NOW = 2026-10-19.
    departure = datetime(2026, 11, 3, 20, tzinfo=UTC)
    source = FakeSource()

    result = forecast_window_for_locations(source, [(30.0, -97.0)], departure, 20_000, now=NOW)

    _, start, end = source.calls[0]
    assert end == datetime(2026, 11, 3, 23, tzinfo=UTC)
    observations = result.locations[0].observations
    assert all(o.risk is not None for o in observations[:4])
    assert all(o.weather.reason == OUTSIDE_COVERAGE for o in observations[4:])
    assert result.coverage_note.startswith("45 of 49 hours are beyond the available forecast")


def test_window_entirely_beyond_horizon_makes_no_request():
    source = FakeSource()

    result = forecast_window_for_locations(source, [(30.0, -97.0)], NOW + timedelta(days=30), 20_000, now=NOW)

    assert source.calls == []
    assert all(o.weather.reason == OUTSIDE_COVERAGE for o in result.locations[0].observations)
    assert result.coverage_note.startswith("49 of 49 hours")


def test_provider_failure_marks_every_observation_unavailable():
    result = forecast_window_for_locations(
        FakeSource(error=weather_unavailable()), [(30.0, -97.0), (31.0, -97.0)], DEPARTURE, 20_000, now=NOW
    )

    for location in result.locations:
        assert all(o.weather.reason == "provider_error" and o.risk is None for o in location.observations)
    assert all(slot.forecast_time is None for slot in result.slots)
