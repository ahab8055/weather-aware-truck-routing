"""Forecasts for fixed locations at every hour from departure to departure + 48 h.

Powers the map's forecast-time slider. Each slot uses the same nearest-hour
policy (30-minute tolerance) and risk engine as route evaluation, so a value
shown for a slot is a real forecast for that hour or explicitly unavailable.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from risk.engine import CheckpointRisk, assess_checkpoint
from weather.errors import WeatherError
from weather.forecast import (
    OUTSIDE_COVERAGE,
    NormalizedWeather,
    WeatherUnavailable,
    forecast_window,
    location_key,
    select_forecast,
)
from weather.open_meteo import HourlySeries

FORECAST_WINDOW_HOURS = 48
WINDOW_STEP_HOURS = 1
MAX_WINDOW_LOCATIONS = 300


class HourlyForecastSource(Protocol):
    def fetch_hourly(
        self, locations: Sequence[tuple[float, float]], start: datetime, end: datetime
    ) -> list[HourlySeries | WeatherError]: ...


@dataclass(frozen=True)
class WindowObservation:
    weather: NormalizedWeather | WeatherUnavailable
    risk: CheckpointRisk | None


@dataclass(frozen=True)
class WindowSlot:
    offset_hours: int
    target_time: datetime
    # Forecast hour actually used for this slot; None if no location had data.
    forecast_time: datetime | None


@dataclass(frozen=True)
class LocationWindow:
    latitude: float
    longitude: float
    observations: tuple[WindowObservation, ...]


@dataclass(frozen=True)
class ForecastWindowResult:
    departure_time: datetime
    load_weight_lbs: float
    slots: tuple[WindowSlot, ...]
    locations: tuple[LocationWindow, ...]
    coverage_note: str | None


def window_targets(departure_time: datetime) -> tuple[datetime, ...]:
    """Slot times: departure, departure + 1 h, ..., departure + 48 h."""
    if departure_time.tzinfo is None or departure_time.utcoffset() is None:
        raise ValueError("departure_time must be timezone-aware")
    return tuple(
        departure_time + timedelta(hours=offset)
        for offset in range(0, FORECAST_WINDOW_HOURS + 1, WINDOW_STEP_HOURS)
    )


def _observe(
    series: HourlySeries | WeatherError | None, target: datetime, load_weight_lbs: float
) -> WindowObservation:
    weather = select_forecast(series, target)
    risk = (
        assess_checkpoint(weather.to_conditions(), load_weight_lbs)
        if isinstance(weather, NormalizedWeather)
        else None
    )
    return WindowObservation(weather=weather, risk=risk)


def _slot_forecast_time(locations: Sequence[LocationWindow], index: int) -> datetime | None:
    for location in locations:
        weather = location.observations[index].weather
        if isinstance(weather, NormalizedWeather):
            return weather.forecast_time
    return None


def _coverage_note(locations: Sequence[LocationWindow], slot_count: int) -> str | None:
    outside = sum(
        1
        for index in range(slot_count)
        if all(
            isinstance(loc.observations[index].weather, WeatherUnavailable)
            and loc.observations[index].weather.reason == OUTSIDE_COVERAGE
            for loc in locations
        )
    )
    if not outside:
        return None
    return (
        f"{outside} of {slot_count} hours are beyond the available forecast "
        "(Open-Meteo serves about 16 days ahead) and have no data."
    )


def forecast_window_for_locations(
    source: HourlyForecastSource,
    locations: Sequence[tuple[float, float]],
    departure_time: datetime,
    load_weight_lbs: float,
    now: datetime | None = None,
) -> ForecastWindowResult:
    """Forecast and risk at each location for every hourly slot of the 48-hour window.

    Nearby locations share one forecast (same grouping as route evaluation) and
    everything is fetched in a single batched call. Output stays aligned to `locations`.
    """
    targets = window_targets(departure_time)
    now = now or datetime.now(UTC)
    keys = list(dict.fromkeys(location_key(lat, lng) for lat, lng in locations))
    window = forecast_window(targets, now)
    forecasts = dict(zip(keys, source.fetch_hourly(keys, *window))) if window and keys else {}

    location_windows = tuple(
        LocationWindow(
            latitude=lat,
            longitude=lng,
            observations=tuple(
                _observe(forecasts.get(location_key(lat, lng)), target, load_weight_lbs)
                for target in targets
            ),
        )
        for lat, lng in locations
    )
    slots = tuple(
        WindowSlot(
            offset_hours=index * WINDOW_STEP_HOURS,
            target_time=target,
            forecast_time=_slot_forecast_time(location_windows, index),
        )
        for index, target in enumerate(targets)
    )
    return ForecastWindowResult(
        departure_time=departure_time,
        load_weight_lbs=load_weight_lbs,
        slots=slots,
        locations=location_windows,
        coverage_note=_coverage_note(location_windows, len(targets)) if location_windows else None,
    )
