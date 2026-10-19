"""Fake Open-Meteo payloads matching the real forecast API structure (no network).

Shape verified against a live response on 2026-10-18 for
hourly=wind_speed_10m,rain,snowfall&wind_speed_unit=mph&precipitation_unit=inch&timeformat=unixtime.
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import httpx

from weather.open_meteo import OpenMeteoClient

BASE_URL = "https://meteo.test"
REAL_UNITS = {"time": "unixtime", "wind_speed_10m": "mp/h", "rain": "inch", "snowfall": "inch"}

Conditions = Callable[[float, float, datetime], tuple[object, object, object]]


def hours(start: datetime, count: int) -> list[datetime]:
    return [start + timedelta(hours=i) for i in range(count)]


def location_payload(
    lat: float,
    lng: float,
    times: list[datetime],
    wind: list,
    rain: list,
    snowfall: list,
    units: dict | None = None,
) -> dict:
    return {
        "latitude": lat,
        "longitude": lng,
        "generationtime_ms": 0.082,
        "utc_offset_seconds": 0,
        "timezone": "GMT",
        "timezone_abbreviation": "GMT",
        "elevation": 152.0,
        "hourly_units": dict(units or REAL_UNITS),
        "hourly": {
            "time": [int(t.timestamp()) for t in times],
            "wind_speed_10m": wind,
            "rain": rain,
            "snowfall": snowfall,
        },
    }


def _parse_hour(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M").replace(tzinfo=UTC)


def calm(lat: float, lng: float, moment: datetime) -> tuple[float, float, float]:
    return (8.0, 0.0, 0.0)


def forecast_handler(
    conditions: Conditions = calm, calls: list | None = None, units: dict | None = None
) -> Callable[[httpx.Request], httpx.Response]:
    """Answer like Open-Meteo: one result per requested coordinate, hourly from start to end."""

    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(request)
        params = request.url.params
        lats = [float(v) for v in params["latitude"].split(",")]
        lngs = [float(v) for v in params["longitude"].split(",")]
        start, end = _parse_hour(params["start_hour"]), _parse_hour(params["end_hour"])
        times = hours(start, int((end - start) / timedelta(hours=1)) + 1)
        items = []
        for lat, lng in zip(lats, lngs):
            columns = list(zip(*(conditions(lat, lng, t) for t in times)))
            items.append(location_payload(lat, lng, times, *map(list, columns), units=units))
        return httpx.Response(200, json=items if len(items) > 1 else items[0])

    return handler


def make_weather_client(handler, **kwargs) -> OpenMeteoClient:
    # Retries never really sleep in tests.
    kwargs.setdefault("sleep", lambda seconds: None)
    return OpenMeteoClient(BASE_URL, transport=httpx.MockTransport(handler), **kwargs)
