import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def clear_cache():
    """Geocoding results are cached; start every test with an empty cache."""
    cache.clear()
    yield
    cache.clear()
