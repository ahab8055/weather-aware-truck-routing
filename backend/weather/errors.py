"""Sanitized weather-provider errors. Messages are fixed strings written here."""


class WeatherError(Exception):
    """A failure to obtain usable forecast data; `code` and `message` are safe to expose."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def __repr__(self) -> str:
        return f"WeatherError(code={self.code!r})"


def weather_timeout() -> WeatherError:
    return WeatherError("weather_timeout", "The weather provider did not respond in time.")


def weather_unavailable() -> WeatherError:
    return WeatherError("weather_unavailable", "The weather provider is unavailable.")


def invalid_weather_data() -> WeatherError:
    return WeatherError(
        "invalid_weather_data", "The weather provider returned data that could not be used."
    )


def invalid_coordinates() -> WeatherError:
    return WeatherError("invalid_coordinates", "The checkpoint coordinates are invalid.")
