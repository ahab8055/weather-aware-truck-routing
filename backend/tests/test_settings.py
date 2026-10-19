import importlib

import pytest

import config.settings


@pytest.fixture
def reload_settings(monkeypatch):
    """Reload the settings module under a modified environment, then restore it."""

    def reload(**env):
        for name, value in env.items():
            monkeypatch.setenv(name, value)
        return importlib.reload(config.settings)

    yield reload
    monkeypatch.undo()
    importlib.reload(config.settings)


def test_https_hardening_is_off_by_default(reload_settings, monkeypatch):
    for name in ("DJANGO_SECURE_SSL_REDIRECT", "DJANGO_SECURE_HSTS_SECONDS", "DJANGO_SECURE_PROXY_SSL_HEADER"):
        monkeypatch.delenv(name, raising=False)

    module = reload_settings()

    assert module.SECURE_SSL_REDIRECT is False
    assert module.SECURE_HSTS_SECONDS == 0
    assert not hasattr(module, "SECURE_PROXY_SSL_HEADER")


def test_https_hardening_from_environment(reload_settings):
    module = reload_settings(
        DJANGO_SECURE_SSL_REDIRECT="true",
        DJANGO_SECURE_HSTS_SECONDS="3600",
        DJANGO_SECURE_PROXY_SSL_HEADER="1",
    )

    assert module.SECURE_SSL_REDIRECT is True
    assert module.SECURE_HSTS_SECONDS == 3600
    assert module.SECURE_PROXY_SSL_HEADER == ("HTTP_X_FORWARDED_PROTO", "https")


def test_production_requires_secret_key(reload_settings, monkeypatch):
    monkeypatch.setenv("DJANGO_DEBUG", "False")
    monkeypatch.setenv("DJANGO_SECRET_KEY", "")

    with pytest.raises(Exception, match="DJANGO_SECRET_KEY must be set"):
        reload_settings()


def test_api_is_stateless_and_public():
    from django.conf import settings

    assert settings.REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"] == []
    assert settings.REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"] == ["rest_framework.permissions.AllowAny"]


def test_geocoding_is_worldwide_by_default(reload_settings, monkeypatch):
    # Ignore the developer's backend/.env so only the code default is tested.
    monkeypatch.setattr("dotenv.load_dotenv", lambda *args, **kwargs: False)
    monkeypatch.delenv("ORS_GEOCODE_COUNTRY", raising=False)
    monkeypatch.setenv("DJANGO_DEBUG", "True")

    assert reload_settings().ORS_GEOCODE_COUNTRY == ""


def test_geocoding_country_can_be_restricted(reload_settings):
    assert reload_settings(ORS_GEOCODE_COUNTRY=" PK ").ORS_GEOCODE_COUNTRY == "PK"
