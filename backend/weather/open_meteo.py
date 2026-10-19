"""Open-Meteo forecast client (HTTP and response-structure validation only).

Requests hourly `wind_speed_10m` (mph, instant value), `rain` (inches, total of
the preceding hour) and `snowfall` (inches of snow depth, total of the
preceding hour) with UTC unix timestamps. Several coordinates are sent per
request; Open-Meteo answers with one result per coordinate, in order.

Transient failures (timeouts, connection errors, HTTP 429 and 5xx) are retried
with a short backoff before the batch is reported unavailable, because Open-Meteo
counts every location against its per-minute limit and route evaluation is
usually followed immediately by the 48-hour heatmap request.
"""

import logging
import math
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from django.conf import settings

from weather.errors import (
    WeatherError,
    invalid_coordinates,
    invalid_weather_data,
    weather_timeout,
    weather_unavailable,
)

logger = logging.getLogger(__name__)

LatLng = tuple[float, float]

FORECAST_PATH = "/v1/forecast"
DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0)
DEFAULT_BATCH_SIZE = 50
DEFAULT_MAX_WORKERS = 4
# Seconds to wait before each retry; one more attempt than entries in total.
RETRY_BACKOFF_SECONDS = (1.0, 2.0)
# A provider-requested Retry-After up to this long is honoured; a longer one is not waited for.
MAX_RETRY_AFTER_SECONDS = 5.0

# Unit strings Open-Meteo reports in `hourly_units` for the requested units.
EXPECTED_HOURLY_UNITS = {"wind_speed_10m": "mp/h", "rain": "inch", "snowfall": "inch"}
HOURLY_VARIABLES = tuple(EXPECTED_HOURLY_UNITS)


@dataclass(frozen=True)
class HourlySeries:
    """Hourly values for one location. Unusable values are None, never zero."""

    times: tuple[datetime, ...]
    wind_speed_mph: tuple[float | None, ...]
    rain_in: tuple[float | None, ...]
    snowfall_in: tuple[float | None, ...]


class OpenMeteoClient:
    """Fetches hourly forecasts for many coordinates using batched, bounded-concurrency requests."""

    def __init__(
        self,
        base_url: str,
        *,
        transport: httpx.BaseTransport | None = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
        max_workers: int = DEFAULT_MAX_WORKERS,
        retry_backoff: Sequence[float] = RETRY_BACKOFF_SECONDS,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._http = httpx.Client(base_url=base_url, timeout=DEFAULT_TIMEOUT, transport=transport)
        self.batch_size = batch_size
        self.max_workers = max_workers
        self._retry_backoff = tuple(retry_backoff)
        self._sleep = sleep

    @classmethod
    def from_settings(cls) -> "OpenMeteoClient":
        return cls(base_url=settings.OPEN_METEO_BASE_URL)

    def close(self) -> None:
        self._http.close()

    def fetch_hourly(
        self, locations: Sequence[LatLng], start: datetime, end: datetime
    ) -> list[HourlySeries | WeatherError]:
        """Hourly forecasts for `locations` between `start` and `end` (inclusive, UTC hours).

        Returns one entry per location, in order: a series, or a WeatherError
        when that location's data could not be obtained.
        """
        results: list[HourlySeries | WeatherError] = [invalid_coordinates()] * len(locations)
        valid = [i for i, location in enumerate(locations) if _valid_coordinate(location)]
        batches = [valid[i : i + self.batch_size] for i in range(0, len(valid), self.batch_size)]
        if not batches:
            return results

        def fetch(batch: list[int]) -> list[HourlySeries | WeatherError]:
            return self._fetch_batch([locations[i] for i in batch], start, end)

        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(batches))) as pool:
            for batch, batch_results in zip(batches, pool.map(fetch, batches)):
                for index, result in zip(batch, batch_results):
                    results[index] = result
        return results

    def _fetch_batch(
        self, batch: Sequence[LatLng], start: datetime, end: datetime
    ) -> list[HourlySeries | WeatherError]:
        params = {
            "latitude": ",".join(f"{lat:.4f}" for lat, _ in batch),
            "longitude": ",".join(f"{lng:.4f}" for _, lng in batch),
            "hourly": ",".join(HOURLY_VARIABLES),
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",
            "timeformat": "unixtime",
            "timezone": "GMT",
            "start_hour": _format_hour(start),
            "end_hour": _format_hour(end),
        }
        try:
            payload = self._request(params)
        except WeatherError as error:
            return [error] * len(batch)

        items = payload if isinstance(payload, list) else [payload]
        if len(items) != len(batch):
            logger.warning("Open-Meteo returned %s results for %s locations", len(items), len(batch))
            return [invalid_weather_data()] * len(batch)
        return [_parse_location(item) for item in items]

    def _request(self, params: dict[str, str]) -> Any:
        delays = iter(self._retry_backoff)
        while True:
            try:
                response = self._attempt(params)
            except _TransientFailure as failure:
                delay = next(delays, None)
                if delay is not None and failure.retry_after is not None:
                    # Waiting less than the provider asked would only fail again.
                    delay = failure.retry_after if failure.retry_after <= MAX_RETRY_AFTER_SECONDS else None
                if delay is None:
                    raise failure.error from None
                logger.info("Retrying Open-Meteo request in %.1f s", delay)
                self._sleep(delay)
                continue
            break
        try:
            return response.json()
        except ValueError:
            logger.warning("Open-Meteo returned invalid JSON")
            raise invalid_weather_data() from None


    def _attempt(self, params: dict[str, str]) -> httpx.Response:
        """One HTTP request; raises _TransientFailure for errors worth retrying."""
        try:
            response = self._http.get(FORECAST_PATH, params=params)
        except httpx.TimeoutException:
            logger.warning("Open-Meteo request timed out")
            raise _TransientFailure(weather_timeout()) from None
        except httpx.HTTPError as error:
            logger.warning("Open-Meteo request failed: %s", type(error).__name__)
            raise _TransientFailure(weather_unavailable()) from None
        if response.is_success:
            return response
        logger.warning("Open-Meteo request rejected: status=%s", response.status_code)
        if response.status_code == 429 or response.is_server_error:
            raise _TransientFailure(weather_unavailable(), _retry_after_seconds(response))
        raise weather_unavailable()


class _TransientFailure(Exception):
    """Internal: a failed attempt that may succeed when repeated."""

    def __init__(self, error: WeatherError, retry_after: float | None = None) -> None:
        super().__init__(error.code)
        self.error = error
        self.retry_after = retry_after


def _retry_after_seconds(response: httpx.Response) -> float | None:
    """Retry-After given in seconds, if present (the HTTP-date form is ignored)."""
    try:
        seconds = float(response.headers.get("Retry-After", ""))
    except ValueError:
        return None
    return seconds if math.isfinite(seconds) and seconds >= 0 else None


def _valid_coordinate(location: Any) -> bool:
    try:
        lat, lng = location
    except (TypeError, ValueError):
        return False
    numbers = all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (lat, lng))
    return (
        numbers
        and math.isfinite(lat)
        and math.isfinite(lng)
        and -90 <= lat <= 90
        and -180 <= lng <= 180
    )


def _format_hour(moment: datetime) -> str:
    if moment.tzinfo is None:
        raise ValueError("start and end must be timezone-aware")
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M")


def _value(raw: Any) -> float | None:
    """A finite number, or None for null, non-numeric or non-finite values."""
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    return float(raw) if math.isfinite(raw) else None


def _parse_location(item: Any) -> HourlySeries | WeatherError:
    try:
        units = item["hourly_units"]
        hourly = item["hourly"]
        if any(units.get(name) != unit for name, unit in EXPECTED_HOURLY_UNITS.items()):
            raise ValueError("unexpected units")
        raw_times = hourly["time"]
        if not isinstance(raw_times, list) or any(
            isinstance(t, bool) or not isinstance(t, int) for t in raw_times
        ):
            raise ValueError("time must be a list of unix seconds")
        if any(b <= a for a, b in zip(raw_times, raw_times[1:])):
            raise ValueError("time must be strictly increasing")
        columns = []
        for name in HOURLY_VARIABLES:
            column = hourly[name]
            if not isinstance(column, list) or len(column) != len(raw_times):
                raise ValueError(f"{name} must align with time")
            columns.append(tuple(_value(v) for v in column))
    except (KeyError, TypeError, ValueError, AttributeError):
        logger.warning("Open-Meteo location result had an unexpected shape or units")
        return invalid_weather_data()

    wind, rain, snowfall = columns
    return HourlySeries(
        times=tuple(datetime.fromtimestamp(t, UTC) for t in raw_times),
        wind_speed_mph=wind,
        rain_in=rain,
        snowfall_in=snowfall,
    )
