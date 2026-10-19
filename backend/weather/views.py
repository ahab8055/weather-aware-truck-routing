from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response

from weather.open_meteo import OpenMeteoClient
from weather.serializers import ForecastWindowRequestSerializer, serialize_forecast_window
from weather.window import forecast_window_for_locations


def build_weather_client() -> OpenMeteoClient:
    return OpenMeteoClient.from_settings()


@api_view(["POST"])
def forecast_window(request: Request) -> Response:
    """Hourly forecast and risk at the given locations for 0-48 h after departure.

    Provider failures do not fail the request: affected observations are
    returned as unavailable, never as zero or Low.
    """
    serializer = ForecastWindowRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    client = build_weather_client()
    try:
        result = forecast_window_for_locations(
            client,
            [(location["latitude"], location["longitude"]) for location in data["locations"]],
            data["departure_time"],
            data["load_weight_lbs"],
        )
    finally:
        client.close()
    return Response(serialize_forecast_window(result))
