import re
from datetime import date, timedelta

import pytest
from django.test import Client
from django.urls import reverse

from apps.councils.models import Council
from apps.spend.models import SpendTransaction


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


@pytest.mark.django_db
def test_html_view_renders_table_for_council(council, rows):
    client = Client()
    response = client.get(reverse("council-spend", kwargs={"slug": council.slug}))

    assert response.status_code == 200
    content = response.content.decode()
    assert "Vendor 00" in content
    assert council.name in content


@pytest.mark.django_db
def test_scraped_beneficiary_name_is_escaped_in_html(council):
    """docs/ARCHITECTURE.md's security plan: scraped text (beneficiary_name,
    description, directorate, category) must never be rendered via |safe or
    mark_safe. A payload injected here proves Django's default auto-escaping
    is still doing the job, not just that nobody wrote |safe today."""
    payload = "<script>alert(1)</script>"
    SpendTransaction.objects.create(
        council=council,
        date=date(2026, 1, 1),
        beneficiary_name=payload,
        amount_gbp="10.00",
    )
    client = Client()
    response = client.get(reverse("council-spend", kwargs={"slug": council.slug}))

    content = response.content.decode()
    assert payload not in content
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in content


@pytest.mark.django_db
def test_html_view_404s_for_unknown_council():
    client = Client()
    response = client.get(reverse("council-spend", kwargs={"slug": "not-a-real-council"}))
    assert response.status_code == 404


@pytest.mark.django_db
def test_html_view_rejects_inverted_date_range(council, rows):
    client = Client()
    response = client.get(
        reverse("council-spend", kwargs={"slug": council.slug}),
        {"date_from": "2026-06-01", "date_to": "2026-01-01"},
    )
    assert response.status_code == 200
    assert "date_from must not be after date_to" in response.content.decode()
    # Filters rejected -- no rows rendered, not a silent partial/misfiltered result.
    assert "Vendor 00" not in response.content.decode()


@pytest.mark.django_db
def test_api_returns_paginated_json(council, rows):
    client = Client()
    response = client.get(reverse("council-transactions", kwargs={"slug": council.slug}))

    assert response.status_code == 200
    data = response.json()
    assert {"next", "previous", "results"} <= data.keys()
    assert len(data["results"]) == 5


@pytest.mark.django_db
def test_api_rejects_inverted_amount_range(council, rows):
    client = Client()
    response = client.get(
        reverse("council-transactions", kwargs={"slug": council.slug}),
        {"amount_min": "500", "amount_max": "10"},
    )
    assert response.status_code == 400
    assert "amount_min" in response.json()["__all__"][0]


@pytest.mark.parametrize("endpoint_name", ["council-spend", "council-transactions"])
@pytest.mark.django_db
def test_sort_toggles_order_on_html_and_api(council, rows, endpoint_name):
    client = Client()
    kwargs = {"slug": council.slug}
    asc = client.get(reverse(endpoint_name, kwargs=kwargs), {"sort": "amount_gbp", "dir": "asc"})
    desc = client.get(reverse(endpoint_name, kwargs=kwargs), {"sort": "amount_gbp", "dir": "desc"})

    assert asc.status_code == 200
    assert desc.status_code == 200

    if endpoint_name == "council-transactions":
        asc_names = [r["beneficiary_name"] for r in asc.json()["results"]]
        desc_names = [r["beneficiary_name"] for r in desc.json()["results"]]
    else:
        # Extraction must preserve document order, not filter a fixed list --
        # membership alone can't distinguish "correct order" from "any order".
        asc_names = re.findall(r"Vendor \d\d", asc.content.decode())
        desc_names = re.findall(r"Vendor \d\d", desc.content.decode())

    assert asc_names == list(reversed(desc_names))
    assert asc_names == sorted(asc_names)


@pytest.mark.django_db
def test_api_pagination_walk_covers_all_rows(council):
    SpendTransaction.objects.bulk_create(
        SpendTransaction(
            council=council,
            date=date(2026, 1, 1) + timedelta(days=i % 300),
            beneficiary_name=f"Bulk Vendor {i:04d}",
            amount_gbp="10.00",
        )
        for i in range(180)
    )
    client = Client()
    url = reverse("council-transactions", kwargs={"slug": council.slug})
    seen = []
    pages = 0
    while url:
        response = client.get(url)
        assert response.status_code == 200
        data = response.json()
        seen.extend(data["results"])
        url = data["next"]
        pages += 1
        assert pages < 20, "pagination walk did not terminate"

    assert pages > 1
    assert len(seen) == 180
    assert len({r["id"] for r in seen}) == 180


@pytest.mark.django_db
def test_category_field_is_disabled_and_has_no_filtering_effect(council, rows):
    """Phase 4 scope explicitly renders Category disabled ('Coming Soon') --
    submitting a value for it must not affect results, since there's no
    server-side handling for it yet."""
    client = Client()
    without = client.get(reverse("council-transactions", kwargs={"slug": council.slug}))
    with_category = client.get(
        reverse("council-transactions", kwargs={"slug": council.slug}), {"category": "Anything"}
    )
    assert without.json()["results"] == with_category.json()["results"]

    html = client.get(reverse("council-spend", kwargs={"slug": council.slug}))
    assert "disabled" in html.content.decode()


@pytest.mark.django_db
def test_beneficiary_search_query_param_is_parameterized_not_interpolated(council, rows):
    """A naive f-string/raw-SQL implementation would either error or behave
    unexpectedly on unescaped SQL metacharacters; the ORM must handle it as
    inert literal text via a bound parameter."""
    malicious = "Vendor'; DROP TABLE spend_spendtransaction; --"
    client = Client()
    response = client.get(
        reverse("council-transactions", kwargs={"slug": council.slug}), {"q": malicious}
    )

    assert response.status_code == 200
    assert response.json()["results"] == []
    # The table must still exist and still hold every row -- proof the
    # input was bound as data, never concatenated into executable SQL.
    assert SpendTransaction.objects.filter(council=council).count() == 5
