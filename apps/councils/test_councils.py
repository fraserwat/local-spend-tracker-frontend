import pytest
from rest_framework.test import APIClient

from apps.councils.models import Council, CouncilCoverage
from apps.councils.selectors import councils_missing_coverage
from apps.spend.models import SpendTransaction

# Deliberately out of real ONS range (E09/E06/E07/E08 etc. are all real
# prefixes) so synthetic test councils can never collide with real seeded
# data or be mistaken for one.
SYNTHETIC_GSS_PREFIX = "E99"


@pytest.mark.django_db
def test_haringey_council_seeded():
    council = Council.objects.get(slug="haringey")
    assert council.gss_code == "E09000014"


@pytest.mark.django_db
def test_councils_api_returns_every_council_across_pages():
    client = APIClient()
    seen = []
    url = "/api/v1/councils/"
    while url:
        response = client.get(url)
        assert response.status_code == 200
        seen.extend(response.data["results"])
        url = response.data["next"]
    assert len(seen) == Council.objects.count()


@pytest.mark.django_db
def test_councils_api_pagination_walk_covers_hundreds_of_councils():
    """The pagination-walk logic must not quietly stop at page one.

    The pilot only ever had 32 councils, comfortably under PAGE_SIZE (100),
    so a test that only exercises page one would pass even if `next` were
    never followed. Bulk-create enough councils to force several pages and
    confirm the walk still surfaces every one of them, not just the first.
    """
    Council.objects.bulk_create(
        Council(
            name=f"Synthetic Council {i:04d}",
            slug=f"synthetic-council-{i:04d}",
            gss_code=f"{SYNTHETIC_GSS_PREFIX}{i:06d}",
        )
        for i in range(250)
    )
    expected_total = Council.objects.count()
    assert expected_total > 250  # sanity check: seeded councils + synthetic ones

    client = APIClient()
    seen = []
    url = "/api/v1/councils/"
    pages_fetched = 0
    # Sane upper bound so a hypothetical cyclical-cursor regression fails
    # fast with a clear assertion instead of hanging the test run in CI.
    max_pages = (expected_total // 10) + 5
    while url:
        assert pages_fetched < max_pages, (
            "pagination walk did not terminate -- possible cursor cycle"
        )
        response = client.get(url)
        assert response.status_code == 200
        seen.extend(response.data["results"])
        url = response.data["next"]
        pages_fetched += 1

    assert pages_fetched > 1
    assert len(seen) == expected_total
    seen_slugs = {row["slug"] for row in seen}
    assert len(seen_slugs) == expected_total  # no duplicates across pages
    assert "synthetic-council-0249" in seen_slugs


@pytest.mark.django_db
def test_councils_missing_coverage_flags_council_with_uncovered_spend():
    council = Council.objects.create(
        name="Synthetic Uncovered",
        slug="synthetic-uncovered",
        gss_code=f"{SYNTHETIC_GSS_PREFIX}000100",
    )
    SpendTransaction.objects.create(
        council=council, date="2026-01-15", beneficiary_name="Acme Ltd", amount_gbp="100.00"
    )

    assert list(councils_missing_coverage()) == [council]


@pytest.mark.django_db
def test_councils_missing_coverage_excludes_properly_covered_council():
    council = Council.objects.create(
        name="Synthetic Covered", slug="synthetic-covered", gss_code=f"{SYNTHETIC_GSS_PREFIX}000200"
    )
    SpendTransaction.objects.create(
        council=council, date="2026-01-15", beneficiary_name="Acme Ltd", amount_gbp="100.00"
    )
    CouncilCoverage.objects.create(council=council)

    assert council not in councils_missing_coverage()


@pytest.mark.django_db
def test_councils_missing_coverage_excludes_council_with_no_spend_at_all():
    """A council with zero transactions has nothing to reconcile yet -- not a data-quality gap."""
    council = Council.objects.create(
        name="Synthetic Empty", slug="synthetic-empty", gss_code=f"{SYNTHETIC_GSS_PREFIX}000300"
    )

    assert council not in councils_missing_coverage()


@pytest.mark.django_db
def test_councils_missing_coverage_excludes_coverage_row_created_ahead_of_data():
    """Coverage can be created before any load (e.g. council onboarded but not
    yet loaded) -- with no transactions yet, it's not a reconciliation gap
    either, regardless of the coverage row already existing."""
    council = Council.objects.create(
        name="Synthetic Preemptive",
        slug="synthetic-preemptive",
        gss_code=f"{SYNTHETIC_GSS_PREFIX}000400",
    )
    CouncilCoverage.objects.create(council=council)

    assert council not in councils_missing_coverage()
