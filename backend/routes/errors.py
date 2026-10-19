"""Sanitized routing errors.

Messages are fixed, user-facing strings written here. Provider response bodies,
request URLs and credentials are never included.
"""

from typing import Any


class RoutingError(Exception):
    """Base class; `code`, `message` and `http_status` are safe to return to clients."""

    code = "routing_error"
    http_status = 502
    default_message = "The routing request could not be completed."

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.default_message
        if code is not None:
            self.code = code
        self.details = details or {}
        super().__init__(self.message)


class RoutingNotConfigured(RoutingError):
    code = "routing_not_configured"
    http_status = 503
    default_message = "Routing is not configured on the server (missing ORS_API_KEY)."


class RoutingTimeout(RoutingError):
    code = "routing_timeout"
    http_status = 504
    default_message = "The routing provider did not respond in time. Please try again."


class RoutingUnavailable(RoutingError):
    code = "routing_unavailable"
    http_status = 502
    default_message = "The routing provider is unavailable. Please try again later."


class RoutingDataError(RoutingError):
    code = "invalid_route_data"
    http_status = 502
    default_message = "The routing provider returned data that could not be used."


class RouteNotFound(RoutingError):
    code = "route_not_found"
    http_status = 422
    default_message = "No drivable truck route was found between these locations."


class LocationNotRoutable(RouteNotFound):
    """One endpoint has no truck-routable road within the provider's snapping radius (ORS 2010)."""

    code = "location_not_routable"
    default_message = "A location is not near a road trucks can use."


class RouteTooLong(RoutingError):
    code = "route_too_long"
    http_status = 422
    default_message = "The route exceeds the routing provider's distance limit."


class LocationNotFound(RoutingError):
    code = "location_not_found"
    http_status = 422
    default_message = "The location could not be found."


class AmbiguousLocation(RoutingError):
    code = "ambiguous_location"
    http_status = 422
    default_message = "The location matches several places."


class SameLocation(RoutingError):
    code = "same_location"
    http_status = 422
    default_message = "Origin and destination resolve to the same place."


class ProviderLimitExceeded(RoutingError):
    """ORS rejected a request parameter as over its limits (ORS error 2004). Internal."""

    code = "provider_limit_exceeded"
    http_status = 422
    default_message = "The request exceeds the routing provider's limits."
