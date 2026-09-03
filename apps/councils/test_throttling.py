from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.test import Client
from django.urls import reverse
from rest_framework.throttling import AnonRateThrottle


@pytest.fixture(autouse=True)
def _clear_throttle_cache():
    # AnonRateThrottle's rate limit is keyed in the default cache -- clear it
    # around each test so tests don't bleed rate-limit state into each other.
    cache.clear()
    yield
    cache.clear()


@pytest.mark.django_db
def test_baseline_anon_throttle_covers_unscoped_api_views():
    """The DEFAULT_THROTTLE_CLASSES baseline (docs/ARCHITECTURE.md's security
    plan only requires rate-limiting export explicitly, but every other public
    /api/v1/ endpoint should still have an abuse backstop) applies to views
    that don't set their own throttle_classes -- council-list here stands in
    for council-coverage and council-transactions, which inherit the same
    default.

    Patches AnonRateThrottle.THROTTLE_RATES directly rather than using
    override_settings: DRF binds THROTTLE_RATES from api_settings once, at
    class-definition time (rest_framework/throttling.py:66), so once any
    earlier test has imported the module under the real 120/min default,
    override_settings can no longer change it for this class.
    """
    client = Client()
    url = reverse("council-list")

    with patch.object(AnonRateThrottle, "THROTTLE_RATES", {"anon": "2/min"}):
        for _ in range(2):
            response = client.get(url)
            assert response.status_code == 200

        third = client.get(url)
        assert third.status_code == 429
