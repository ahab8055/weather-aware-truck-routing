from django.urls import path

from routes.views import location_suggestions, route_candidates, route_evaluation

urlpatterns = [
    path("candidates/", route_candidates, name="route-candidates"),
    path("evaluate/", route_evaluation, name="route-evaluate"),
    path("locations/suggest/", location_suggestions, name="route-location-suggest"),
]
