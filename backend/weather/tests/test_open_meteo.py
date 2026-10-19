import math
import threading
from datetime import UTC, datetime, timedelta, timezone

import httpx
import pytest

from weather.errors import WeatherError
from weather.open_meteo import HourlySeries
from weather.tests.open_meteo_fixtures import (
    REAL_UNITS,
    forecast_handler,
    hours,
    location_payload,
    make_weather_client,
)

START = datetime(2026, 10, 19, 13, tzinfo=UTC)
END = datetime(2026, 10, 19, 16, tzinfo=UTC)
TIMES = hours(START, 4)


def respond(payload, status=200):
    return lambda request: httpx.Response(status, json=payload)


def test_parses_single_location_object_with_utc_times_and_units():
    payload = location_payload(
        39.75, -104.99, TIMES, [4.9, 26.3, 47.0, 55.2], [0.0, 0.12, 0.3, 0.55], [0.0, 0.0, 0.6, 2.4]
    )

    (series,) = make_weather_client(respond(payload)).fetch_hourly([(39.75, -104.99)], START, END)

    assert isinstance(series, HourlySeries)
    assert series.times == tuple(TIMES)
    assert all(t.tzinfo is UTC for t in series.times)
    # Values pass through unchanged: mph and inches were requested from the provider.
    assert series.wind_speed_mph == (4.9, 26.3, 47.0, 55.2)
    assert series.rain_in == (0.0, 0.12, 0.3, 0.55)
    assert series.snowfall_in == (0.0, 0.0, 0.6, 2.4)


def test_parses_list_response_in_request_order():
    payload = [
        location_payload(30.0, -97.0, TIMES, [1, 2, 3, 4], [0] * 4, [0] * 4),
        location_payload(31.0, -97.0, TIMES, [10, 20, 30, 40], [0] * 4, [0] * 4),
    ]

    first, second = make_weather_client(respond(payload)).fetch_hourly(
        [(30.0, -97.0), (31.0, -97.0)], START, END
    )

    assert first.wind_speed_mph == (1, 2, 3, 4)
    assert second.wind_speed_mph == (10, 20, 30, 40)


def test_request_parameters():
    calls = []
    client = make_weather_client(forecast_handler(calls=calls))

    client.fetch_hourly([(30.0, -97.0), (31.25, -96.5)], START, END)

    params = calls[0].url.params
    assert calls[0].url.path == "/v1/forecast"
    assert params["latitude"] == "30.0000,31.2500"
    assert params["longitude"] == "-97.0000,-96.5000"
    assert params["hourly"] == "wind_speed_10m,rain,snowfall"
    assert params["wind_speed_unit"] == "mph"
    assert params["precipitation_unit"] == "inch"
    assert params["timeformat"] == "unixtime"
    assert params["timezone"] == "GMT"
    assert params["start_hour"] == "2026-10-19T13:00"
    assert params["end_hour"] == "2026-10-19T16:00"
    assert "apikey" not in params


def test_non_utc_window_is_sent_in_utc():
    calls = []
    client = make_weather_client(forecast_handler(calls=calls))
    central = timezone(timedelta(hours=-5))
    client.fetch_hourly([(30.0, -97.0)], START.astimezone(central), END.astimezone(central))

    assert calls[0].url.params["start_hour"] == "2026-10-19T13:00"


def test_batches_locations_with_bounded_concurrency():
    calls = []
    active = {"now": 0, "max": 0}
    lock = threading.Lock()
    inner = forecast_handler(calls=calls)

    def handler(request):
        with lock:
            active["now"] += 1
            active["max"] = max(active["max"], active["now"])
        try:
            return inner(request)
        finally:
            with lock:
                active["now"] -= 1

    locations = [(30 + i * 0.01, -97.0) for i in range(120)]
    results = make_weather_client(handler, batch_size=50, max_workers=2).fetch_hourly(
        locations, START, END
    )

    assert len(calls) == 3
    assert sorted(len(c.url.params["latitude"].split(",")) for c in calls) == [20, 50, 50]
    assert active["max"] <= 2
    assert all(isinstance(r, HourlySeries) for r in results)


@pytest.mark.parametrize(
    "units",
    [
        {**REAL_UNITS, "wind_speed_10m": "km/h"},
        {**REAL_UNITS, "snowfall": "cm"},
        {**REAL_UNITS, "rain": "mm"},
        {"time": "unixtime"},
    ],
)
def test_unexpected_units_are_rejected(units):
    payload = location_payload(30, -97, TIMES, [1] * 4, [0] * 4, [0] * 4, units=units)

    (result,) = make_weather_client(respond(payload)).fetch_hourly([(30, -97)], START, END)

    assert isinstance(result, WeatherError)
    assert result.code == "invalid_weather_data"


def _with_hourly(**overrides):
    payload = location_payload(30, -97, TIMES, [1] * 4, [0] * 4, [0] * 4)
    payload["hourly"].update(overrides)
    return payload


@pytest.mark.parametrize(
    "payload",
    [
        {"hourly_units": REAL_UNITS},
        _with_hourly(rain=[0, 0, 0]),
        _with_hourly(snowfall=None),
        _with_hourly(time="1792414800"),
        _with_hourly(time=[1792414800, 1792414800, 1792418400, 1792422000]),
        _with_hourly(time=[1792414800.5, 1792418400, 1792422000, 1792425600]),
        {k: v for k, v in _with_hourly().items() if k != "hourly"},
        "not an object",
    ],
)
def test_malformed_location_results_are_rejected(payload):
    (result,) = make_weather_client(respond(payload)).fetch_hourly([(30, -97)], START, END)

    assert isinstance(result, WeatherError)
    assert result.code == "invalid_weather_data"


def test_missing_variable_key_is_rejected():
    payload = location_payload(30, -97, TIMES, [1] * 4, [0] * 4, [0] * 4)
    del payload["hourly"]["snowfall"]

    (result,) = make_weather_client(respond(payload)).fetch_hourly([(30, -97)], START, END)

    assert isinstance(result, WeatherError)


def test_null_nan_infinite_and_non_numeric_values_become_none_not_zero():
    text = (
        '{"hourly_units": {"time": "unixtime", "wind_speed_10m": "mp/h", "rain": "inch", '
        '"snowfall": "inch"}, "hourly": {"time": [1792414800, 1792418400, 1792422000, 1792425600], '
        '"wind_speed_10m": [null, NaN, Infinity, 12.5], "rain": [0.0, "0.2", -Infinity, true], '
        '"snowfall": [0.0, 0, null, 0.4]}}'
    )
    client = make_weather_client(lambda request: httpx.Response(200, text=text))

    (series,) = client.fetch_hourly([(30, -97)], START, END)

    assert series.wind_speed_mph == (None, None, None, 12.5)
    assert series.rain_in == (0.0, None, None, None)
    assert series.snowfall_in == (0.0, 0.0, None, 0.4)


def raise_(exception):
    def handler(request):
        raise exception

    return handler


@pytest.mark.parametrize(
    ("handler", "code"),
    [
        (raise_(httpx.ReadTimeout("slow")), "weather_timeout"),
        (raise_(httpx.ConnectTimeout("slow")), "weather_timeout"),
        (raise_(httpx.ConnectError("refused")), "weather_unavailable"),
        (
            respond({"error": True, "reason": "Parameter 'start_hour' is out of allowed range"}, 400),
            "weather_unavailable",
        ),
        (respond({"error": True, "reason": "internal"}, 500), "weather_unavailable"),
        (respond({"error": True}, 429), "weather_unavailable"),
        (lambda request: httpx.Response(200, text="<html>"), "invalid_weather_data"),
        (respond([]), "invalid_weather_data"),
    ],
)
def test_transport_and_http_failures_mark_every_location(handler, code):
    results = make_weather_client(handler).fetch_hourly([(30, -97), (31, -97)], START, END)

    assert [r.code for r in results] == [code, code]
    for result in results:
        assert "allowed range" not in result.message
        assert "internal" not in result.message
        assert result.__cause__ is None


def test_failed_batch_only_affects_its_own_locations():
    good = forecast_handler()

    def handler(request):
        if request.url.params["latitude"].startswith("31"):
            return httpx.Response(500)
        return good(request)

    locations = [(30.0, -97.0), (30.5, -97.0), (31.0, -97.0), (31.5, -97.0)]
    results = make_weather_client(handler, batch_size=2).fetch_hourly(locations, START, END)

    assert [isinstance(r, HourlySeries) for r in results] == [True, True, False, False]


@pytest.mark.parametrize("location", [(95.0, -97.0), (30.0, -181.0), (math.nan, 0.0), (30.0, math.inf)])
def test_invalid_coordinates_are_not_sent(location):
    calls = []
    client = make_weather_client(forecast_handler(calls=calls))

    valid, invalid = client.fetch_hourly([(30.0, -97.0), location], START, END)

    assert isinstance(valid, HourlySeries)
    assert invalid.code == "invalid_coordinates"
    assert calls[0].url.params["latitude"] == "30.0000"


def test_no_valid_locations_makes_no_request():
    calls = []
    client = make_weather_client(forecast_handler(calls=calls))

    assert client.fetch_hourly([], START, END) == []
    assert client.fetch_hourly([(100.0, 0.0)], START, END)[0].code == "invalid_coordinates"
    assert calls == []


def flaky(failures, then):
    """Handler that answers with each of `failures` in turn, then delegates to `then`."""
    pending = list(failures)
    calls = []

    def handler(request):
        calls.append(request)
        if pending:
            failure = pending.pop(0)
            if isinstance(failure, Exception):
                raise failure
            return failure
        return then(request)

    return handler, calls


@pytest.mark.parametrize(
    "failure",
    [
        httpx.Response(429, json={"error": True, "reason": "Minutely API request limit exceeded"}),
        httpx.Response(500),
        httpx.Response(503),
        httpx.ReadTimeout("slow"),
        httpx.ConnectError("refused"),
    ],
)
def test_transient_failures_are_retried_until_success(failure):
    handler, calls = flaky([failure, failure], forecast_handler())
    sleeps = []
    client = make_weather_client(handler, sleep=sleeps.append)

    results = client.fetch_hourly([(30, -97), (31, -97)], START, END)

    assert all(isinstance(r, HourlySeries) for r in results)
    assert len(calls) == 3
    assert sleeps == [1.0, 2.0]


def test_gives_up_after_the_last_retry():
    handler, calls = flaky([httpx.Response(503)] * 5, forecast_handler())
    sleeps = []

    results = make_weather_client(handler, sleep=sleeps.append).fetch_hourly([(30, -97)], START, END)

    assert results[0].code == "weather_unavailable"
    assert len(calls) == 3
    assert sleeps == [1.0, 2.0]


def test_client_errors_are_not_retried():
    handler, calls = flaky([httpx.Response(400, json={"error": True})], forecast_handler())

    results = make_weather_client(handler).fetch_hourly([(30, -97)], START, END)

    assert results[0].code == "weather_unavailable"
    assert len(calls) == 1


def test_short_retry_after_is_honoured_and_long_one_is_not_waited_for():
    short, short_calls = flaky([httpx.Response(429, headers={"Retry-After": "3"})], forecast_handler())
    sleeps = []
    assert isinstance(
        make_weather_client(short, sleep=sleeps.append).fetch_hourly([(30, -97)], START, END)[0],
        HourlySeries,
    )
    assert sleeps == [3.0]

    long, long_calls = flaky([httpx.Response(429, headers={"Retry-After": "60"})], forecast_handler())
    sleeps = []
    result = make_weather_client(long, sleep=sleeps.append).fetch_hourly([(30, -97)], START, END)[0]
    assert result.code == "weather_unavailable"
    assert sleeps == []
    assert len(long_calls) == 1


def test_retry_after_does_not_extend_the_retry_budget():
    responses = [httpx.Response(429, headers={"Retry-After": "1"})] * 5
    handler, calls = flaky(responses, forecast_handler())

    result = make_weather_client(handler).fetch_hourly([(30, -97)], START, END)[0]

    assert result.code == "weather_unavailable"
    assert len(calls) == 3
