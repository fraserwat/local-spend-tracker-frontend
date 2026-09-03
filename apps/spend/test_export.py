import csv
from datetime import date, timedelta
from io import StringIO

import pytest
from django.core.cache import cache
from django.test import Client
from django.urls import reverse

from apps.councils.models import Council
from apps.spend.models import SpendTransaction
from apps.spend.services import export as export_module


@pytest.fixture(autouse=True)
def _clear_throttle_cache():
    # ExportRateThrottle's rate limit is keyed in the default cache -- clear
    # it around each test so tests don't bleed rate-limit state into each other.
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def council():
    return Council.objects.get(slug="haringey")


@pytest.fixture
def rows(council):
    base = date(2026, 1, 1)
    return [
        SpendTransaction.objects.create(
            council=council,
            date=base + timedelta(days=i),
            beneficiary_name=f"Vendor {i:02d}",
            amount_gbp=f"{(i + 1) * 10}.00",
        )
        for i in range(5)
    ]


def _csv_body_rows(response) -> list[list[str]]:
    content = b"".join(response.streaming_content).decode()
    rows = list(csv.reader(StringIO(content)))
    return rows[1:]  # drop header


@pytest.mark.parametrize(
    "endpoint_name,params",
    [
        ("council-spend", {"export": "csv"}),
        ("council-transactions-export", {}),
    ],
)
@pytest.mark.django_db
def test_unfiltered_export_matches_db_count(council, rows, endpoint_name, params):
    client = Client()
    response = client.get(reverse(endpoint_name, kwargs={"slug": council.slug}), params)

    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv"
    assert (
        response["Content-Disposition"] == f'attachment; filename="{council.slug}-transactions.csv"'
    )
    body_rows = _csv_body_rows(response)
    assert len(body_rows) == SpendTransaction.objects.filter(council=council).count() == 5


@pytest.mark.parametrize(
    "endpoint_name,extra_params",
    [
        ("council-spend", {"export": "csv"}),
        ("council-transactions-export", {}),
    ],
)
@pytest.mark.django_db
def test_filtered_export_only_includes_matching_rows(council, rows, endpoint_name, extra_params):
    client = Client()
    params = {"amount_min": "40", **extra_params}
    response = client.get(reverse(endpoint_name, kwargs={"slug": council.slug}), params)

    assert response.status_code == 200
    body_rows = _csv_body_rows(response)
    # amount_gbp = (i+1)*10 for i in 0..4 -> 10,20,30,40,50; amount_min=40 keeps 2 rows.
    assert len(body_rows) == 2
    assert all(float(row[2]) >= 40 for row in body_rows)


@pytest.mark.django_db
def test_export_respects_row_cap(council, rows, monkeypatch):
    monkeypatch.setattr(export_module, "CSV_EXPORT_ROW_CAP", 3)
    client = Client()
    response = client.get(
        reverse("council-spend", kwargs={"slug": council.slug}), {"export": "csv"}
    )

    assert len(_csv_body_rows(response)) == 3


@pytest.mark.parametrize(
    "endpoint_name,extra_params",
    [
        ("council-spend", {"export": "csv"}),
        ("council-transactions-export", {}),
    ],
)
@pytest.mark.django_db
def test_export_unknown_council_404s(endpoint_name, extra_params):
    client = Client()
    response = client.get(
        reverse(endpoint_name, kwargs={"slug": "not-a-real-council"}), extra_params
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_html_export_with_invalid_filters_falls_back_to_error_render(council, rows):
    client = Client()
    response = client.get(
        reverse("council-spend", kwargs={"slug": council.slug}),
        {"export": "csv", "date_from": "2026-06-01", "date_to": "2026-01-01"},
    )

    assert response.status_code == 200
    assert response["Content-Type"] != "text/csv"
    assert "date_from must not be after date_to" in response.content.decode()


@pytest.mark.django_db
def test_api_export_rejects_invalid_filters(council, rows):
    client = Client()
    response = client.get(
        reverse("council-transactions-export", kwargs={"slug": council.slug}),
        {"amount_min": "500", "amount_max": "10"},
    )
    assert response.status_code == 400


@pytest.mark.parametrize(
    "endpoint_name,params",
    [
        ("council-spend", {"export": "csv"}),
        ("council-transactions-export", {}),
    ],
)
@pytest.mark.django_db
def test_sixth_rapid_export_request_is_throttled(council, rows, endpoint_name, params):
    client = Client()
    url = reverse(endpoint_name, kwargs={"slug": council.slug})

    for _ in range(5):
        response = client.get(url, params)
        assert response.status_code == 200

    sixth = client.get(url, params)
    assert sixth.status_code == 429
