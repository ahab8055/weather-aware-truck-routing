from datetime import UTC, datetime, timedelta, timezone

import pytest

from risk.engine import WeatherConditions, assess_checkpoint
from risk.levels import RiskLevel
from weather.errors import invalid_weather_data, weather_timeout
from weather.forecast import (
    INVALID_PROVIDER_DATA,
    MISSING_VALUES,
    OUTSIDE_COVERAGE,
    PROVIDER_ERROR,
    NormalizedWeather,
    WeatherUnavailable,
    forecast_window,
    location_key,
    select_forecast,
)
from weather.open_meteo import HourlySeries

T13 = datetime(2026, 10, 19, 13, tzinfo=UTC)
CENTRAL = timezone(timedelta(hours=-5))


def series(start=T13, wind=(5.0, 30.0, 40.0), rain=(0.0, 0.2, 0.4), snow=(0.0, 0.7, 1.5)):
    times = tuple(start + timedelta(hours=i) for i in range(len(wind)))
    return HourlySeries(times=times, wind_speed_mph=wind, rain_in=rain, snowfall_in=snow)


@pytest.mark.parametrize(
    ("eta", "expected_hour"),
    [
        (T13, 13),
        (T13 + timedelta(minutes=10), 13),
        (T13 + timedelta(minutes=29, seconds=59), 13),
        (T13 + timedelta(minutes=30), 14),  # tie -> later hour
        (T13 + timedelta(minutes=50), 14),
        (T13 + timedelta(hours=1), 14),
        (T13 + timedelta(hours=2, minutes=30), 15),  # 30 min after last hour: still covered
        (T13 - timedelta(minutes=30), 13),  # 30 min before first hour: still covered
    ],
)
def test_selects_nearest_forecast_hour(eta, expected_hour):
    weather = select_forecast(series(), eta)

    assert isinstance(weather, NormalizedWeather)
    assert weather.forecast_time == T13.replace(hour=expected_hour)


def test_eta_with_offset_is_compared_in_utc():
    # 08:40 at -05:00 is 13:40 UTC -> nearest hour 14:00 UTC.
    eta = datetime(2026, 10, 19, 8, 40, tzinfo=CENTRAL)

    weather = select_forecast(series(), eta)

    assert weather.forecast_time == datetime(2026, 10, 19, 14, tzinfo=UTC)
    assert (weather.wind_speed_mph, weather.rain_in_per_hr, weather.snowfall_in_per_hr) == (30.0, 0.2, 0.7)


@pytest.mark.parametrize(
    "eta",
    [
        T13 - timedelta(minutes=31),
        T13 + timedelta(hours=2, minutes=31),
        T13 + timedelta(days=20),
    ],
)
def test_eta_outside_coverage_is_unavailable(eta):
    weather = select_forecast(series(), eta)

    assert isinstance(weather, WeatherUnavailable)
    assert weather.reason == OUTSIDE_COVERAGE


@pytest.mark.parametrize("source", [None, series(wind=(), rain=(), snow=())])
def test_no_series_is_outside_coverage(source):
    assert select_forecast(source, T13).reason == OUTSIDE_COVERAGE


def test_gap_in_hourly_times_is_not_bridged():
    times = (T13, T13 + timedelta(hours=3))
    gappy = HourlySeries(times=times, wind_speed_mph=(5, 5), rain_in=(0, 0), snowfall_in=(0, 0))

    assert select_forecast(gappy, T13 + timedelta(hours=1, minutes=30)).reason == OUTSIDE_COVERAGE


@pytest.mark.parametrize(
    "overrides",
    [
        {"wind": (None, 30.0, 40.0)},
        {"rain": (None, 0.2, 0.4)},
        {"snow": (None, 0.7, 1.5)},
        {"rain": (-0.1, 0.2, 0.4)},
        {"wind": (float("nan"), 30.0, 40.0)},
    ],
)
def test_missing_values_are_unavailable_not_zero(overrides):
    weather = select_forecast(series(**overrides), T13)

    assert isinstance(weather, WeatherUnavailable)
    assert weather.reason == MISSING_VALUES
    assert weather.forecast_time == T13


def test_missing_value_does_not_fall_back_to_neighbouring_hour():
    weather = select_forecast(series(wind=(5.0, None, 40.0)), T13 + timedelta(minutes=55))

    assert weather.reason == MISSING_VALUES


def test_explicit_zero_values_are_zero():
    weather = select_forecast(series(wind=(0.0, 0, 0), rain=(0.0, 0, 0), snow=(0.0, 0, 0)), T13)

    assert (weather.wind_speed_mph, weather.rain_in_per_hr, weather.snowfall_in_per_hr) == (0, 0, 0)


def test_provider_errors_map_to_reasons():
    assert select_forecast(weather_timeout(), T13).reason == PROVIDER_ERROR
    assert select_forecast(invalid_weather_data(), T13).reason == INVALID_PROVIDER_DATA


def test_snowfall_depth_in_inches_is_used_directly_as_inches_per_hour():
    # Open-Meteo snowfall = snow depth fallen in the preceding hour; with
    # precipitation_unit=inch, 2.4 means 2.4 in of snow in one hour -> 2.4 in/hr.
    weather = select_forecast(series(wind=(5.0,), rain=(0.0,), snow=(2.4,)), T13)
    conditions = weather.to_conditions()

    assert conditions == WeatherConditions(wind_speed_mph=5.0, rain_in_per_hr=0.0, snow_in_per_hr=2.4)
    assert assess_checkpoint(conditions, 20_000).snow is RiskLevel.SEVERE


def test_to_conditions_feeds_risk_engine_with_matching_units():
    weather = select_forecast(series(wind=(47.0,), rain=(0.3,), snow=(0.0,)), T13)

    risk = assess_checkpoint(weather.to_conditions(), 35_000)

    assert (risk.wind, risk.rain) == (RiskLevel.SEVERE, RiskLevel.HIGH)
    assert risk.overall is RiskLevel.NO_TRAVEL  # wind >= 45 mph and load > 30,000 lb


NOW = datetime(2026, 10, 18, 9, 15, tzinfo=UTC)


def test_window_rounds_to_whole_hours_in_utc():
    etas = [datetime(2026, 10, 19, 8, 10, tzinfo=CENTRAL), datetime(2026, 10, 19, 11, 45, tzinfo=CENTRAL)]

    assert forecast_window(etas, NOW) == (
        datetime(2026, 10, 19, 13, tzinfo=UTC),
        datetime(2026, 10, 19, 17, tzinfo=UTC),
    )


def test_window_on_exact_hours_is_not_widened():
    assert forecast_window([T13, T13 + timedelta(hours=2)], NOW) == (T13, T13 + timedelta(hours=2))


def test_window_is_clipped_to_forecast_horizon():
    etas = [datetime(2026, 11, 2, 20, tzinfo=UTC), datetime(2026, 11, 4, 6, tzinfo=UTC)]

    assert forecast_window(etas, NOW) == (
        datetime(2026, 11, 2, 20, tzinfo=UTC),
        datetime(2026, 11, 2, 23, tzinfo=UTC),
    )


def test_window_entirely_beyond_horizon_is_none():
    assert forecast_window([datetime(2026, 11, 3, 1, tzinfo=UTC)], NOW) is None


def test_window_entirely_too_far_in_past_is_none():
    assert forecast_window([datetime(2026, 7, 1, tzinfo=UTC)], NOW) is None


def test_location_key_groups_nearby_points():
    assert location_key(30.0012, -97.0049) == location_key(29.9951, -96.9951) == (30.0, -97.0)
    assert location_key(30.0, -97.0) != location_key(30.02, -97.0)
