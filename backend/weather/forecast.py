"""Selecting and normalizing the forecast hour for a checkpoint ETA (pure logic).

Policy: use the hourly timestamp nearest to the ETA (compared in UTC). On an
exact half-hour tie the later hour wins, because Open-Meteo's rain and snowfall
at hour T are totals for the hour ending at T, which then contains the ETA.
The selected hour must be within 30 minutes of the ETA; otherwise the
checkpoint is outside forecast coverage. Missing values are never replaced
by zero or by a neighbouring hour.
"""

import math
from bisect import bisect_left
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from risk.engine import WeatherConditions
from weather.errors import WeatherError
from weather.open_meteo import HourlySeries

FORECAST_HOUR_TOLERANCE = timedelta(minutes=30)
# Open-Meteo accepts hours from 92 days back to 16 days ahead (UTC calendar days).
FORECAST_DAYS_LIMIT = 16
PAST_DAYS_LIMIT = 92
# Checkpoints rounding to the same 0.01° (~1.1 km) share one forecast request.
COORDINATE_DECIMALS = 2

OUTSIDE_COVERAGE = "outside_forecast_coverage"
MISSING_VALUES = "missing_values"
PROVIDER_ERROR = "provider_error"
INVALID_PROVIDER_DATA = "invalid_provider_data"
INVALID_COORDINATES = "invalid_coordinates"

_ERROR_REASONS = {
    "invalid_weather_data": INVALID_PROVIDER_DATA,
    "invalid_coordinates": INVALID_COORDINATES,
}


@dataclass(frozen=True)
class NormalizedWeather:
    """Forecast used for a checkpoint, in the units the risk engine expects."""

    forecast_time: datetime
    wind_speed_mph: float
    rain_in_per_hr: float
    snowfall_in_per_hr: float

    def to_conditions(self) -> WeatherConditions:
        return WeatherConditions(
            wind_speed_mph=self.wind_speed_mph,
            rain_in_per_hr=self.rain_in_per_hr,
            snow_in_per_hr=self.snowfall_in_per_hr,
        )


@dataclass(frozen=True)
class WeatherUnavailable:
    """Why no usable forecast exists for a checkpoint."""

    reason: str
    message: str
    forecast_time: datetime | None = None


def location_key(latitude: float, longitude: float) -> tuple[float, float]:
    """Rounded coordinates used to share one forecast between nearby checkpoints."""
    return (round(latitude, COORDINATE_DECIMALS), round(longitude, COORDINATE_DECIMALS))


def _floor_hour(moment: datetime) -> datetime:
    return moment.astimezone(UTC).replace(minute=0, second=0, microsecond=0)


def _ceil_hour(moment: datetime) -> datetime:
    floored = _floor_hour(moment)
    return floored if floored == moment.astimezone(UTC) else floored + timedelta(hours=1)


def forecast_window(etas: Sequence[datetime], now: datetime) -> tuple[datetime, datetime] | None:
    """UTC hour range covering `etas`, clipped to what Open-Meteo serves; None if none of it is."""
    if not etas:
        return None
    today = now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    # One day of margin on the past limit guards against provider/server date skew.
    earliest = today - timedelta(days=PAST_DAYS_LIMIT - 1)
    latest = today + timedelta(days=FORECAST_DAYS_LIMIT) - timedelta(hours=1)
    start = max(_floor_hour(min(etas)), earliest)
    end = min(_ceil_hour(max(etas)), latest)
    return (start, end) if start <= end else None


def unavailable_from_error(error: WeatherError) -> WeatherUnavailable:
    return WeatherUnavailable(reason=_ERROR_REASONS.get(error.code, PROVIDER_ERROR), message=error.message)


def select_forecast(
    series: HourlySeries | WeatherError | None, eta: datetime
) -> NormalizedWeather | WeatherUnavailable:
    """Forecast for the hour nearest `eta`, or the reason none can be used."""
    if isinstance(series, WeatherError):
        return unavailable_from_error(series)
    outside = WeatherUnavailable(
        OUTSIDE_COVERAGE, "The ETA is outside the available forecast period."
    )
    if series is None or not series.times:
        return outside

    eta_utc = eta.astimezone(UTC)
    times = series.times
    index = bisect_left(times, eta_utc)
    if index == len(times) or (index > 0 and eta_utc - times[index - 1] < times[index] - eta_utc):
        index -= 1
    forecast_time = times[index]
    if abs(forecast_time - eta_utc) > FORECAST_HOUR_TOLERANCE:
        return outside

    values = (series.wind_speed_mph[index], series.rain_in[index], series.snowfall_in[index])
    if any(v is None or not math.isfinite(v) or v < 0 for v in values):
        return WeatherUnavailable(
            MISSING_VALUES,
            "The forecast for this hour is missing wind, rain or snowfall values.",
            forecast_time=forecast_time,
        )
    wind, rain, snowfall = values
    return NormalizedWeather(
        forecast_time=forecast_time,
        wind_speed_mph=wind,
        rain_in_per_hr=rain,
        snowfall_in_per_hr=snowfall,
    )
