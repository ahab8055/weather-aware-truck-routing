from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response

from routes.errors import RoutingError
from routes.evaluation import evaluate_routes
from routes.ors import ORSClient
from routes.serializers import (
    LocationSuggestionQuerySerializer,
    RouteCandidatesRequestSerializer,
    serialize_location_suggestions,
    serialize_route_candidates,
    serialize_route_evaluation,
    serialize_routing_error,
)
from routes.services import RouteRequest, plan_route_candidates
from weather.open_meteo import OpenMeteoClient


def build_ors_client() -> ORSClient:
    return ORSClient.from_settings()


def build_weather_client() -> OpenMeteoClient:
    return OpenMeteoClient.from_settings()


def _validated_route_request(request: Request) -> RouteRequest:
    serializer = RouteCandidatesRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    return RouteRequest(**serializer.validated_data)


@api_view(["POST"])
def route_candidates(request: Request) -> Response:
    """Geocode origin/destination, fetch up to three truck routes and their checkpoints."""
    route_request = _validated_route_request(request)

    client = build_ors_client()
    try:
        result = plan_route_candidates(client, route_request)
    except RoutingError as error:
        return Response(serialize_routing_error(error), status=error.http_status)
    finally:
        client.close()
    return Response(serialize_route_candidates(result))


@api_view(["POST"])
def route_evaluation(request: Request) -> Response:
    """Route candidates plus checkpoint forecasts, risk, route summaries and a recommendation.

    Weather failures do not fail the request: affected checkpoints are marked
    unavailable and their routes are not recommended.
    """
    route_request = _validated_route_request(request)

    ors_client = build_ors_client()
    try:
        candidates = plan_route_candidates(ors_client, route_request)
    except RoutingError as error:
        return Response(serialize_routing_error(error), status=error.http_status)
    finally:
        ors_client.close()

    weather_client = build_weather_client()
    try:
        evaluation = evaluate_routes(candidates, weather_client)
    finally:
        weather_client.close()
    return Response(serialize_route_evaluation(evaluation))


# Shorter queries match too broadly to be useful and waste provider quota.
MIN_SUGGESTION_QUERY_LENGTH = 3
MAX_SUGGESTIONS = 5


@api_view(["GET"])
def location_suggestions(request: Request) -> Response:
    """Autocomplete suggestions for the origin/destination fields (`?q=`)."""
    serializer = LocationSuggestionQuerySerializer(data=request.query_params)
    serializer.is_valid(raise_exception=True)
    query = serializer.validated_data["q"]
    if len(query) < MIN_SUGGESTION_QUERY_LENGTH:
        return Response(serialize_location_suggestions(query, []))

    client = build_ors_client()
    try:
        candidates = client.autocomplete(query, limit=MAX_SUGGESTIONS)
    except RoutingError as error:
        return Response(serialize_routing_error(error), status=error.http_status)
    finally:
        client.close()
    return Response(serialize_location_suggestions(query, candidates))
