from django.urls import reverse
from rest_framework.test import APIClient


def test_health_returns_ok():
    response = APIClient().get(reverse("health"), HTTP_ACCEPT="application/json")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_rejects_post():
    response = APIClient().post(reverse("health"))

    assert response.status_code == 405


def test_cors_allows_frontend_origin(settings):
    origin = settings.CORS_ALLOWED_ORIGINS[0]

    response = APIClient().get(reverse("health"), HTTP_ORIGIN=origin)

    assert response.headers["Access-Control-Allow-Origin"] == origin
