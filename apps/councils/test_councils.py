import pytest
from rest_framework.test import APIClient

from apps.councils.models import Council


@pytest.mark.django_db
def test_council_count_is_32():
    assert Council.objects.count() == 32


@pytest.mark.django_db
def test_councils_api_returns_32_results():
    response = APIClient().get("/api/v1/councils/")
    assert response.status_code == 200
    assert len(response.data["results"]) == 32
