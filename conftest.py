import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def _clear_throttle_cache():
    # DRF throttle rate limits are keyed in the default cache -- clear it
    # around every test so rate-limit state (or any other cache key) can't
    # bleed from one test into the next.
    cache.clear()
    yield
    cache.clear()
