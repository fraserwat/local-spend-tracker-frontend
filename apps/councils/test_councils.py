import pytest
from django.test import Client
from django.urls import reverse
from rest_framework.test import APIClient

from apps.councils.models import Council, CouncilCoverage, Region
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
            region=Region.LONDON,
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
        region=Region.LONDON,
    )
    SpendTransaction.objects.create(
        council=council, date="2026-01-15", beneficiary_name="Acme Ltd", amount_gbp="100.00"
    )

    assert list(councils_missing_coverage()) == [council]


@pytest.mark.django_db
def test_councils_missing_coverage_excludes_properly_covered_council():
    council = Council.objects.create(
        name="Synthetic Covered",
        slug="synthetic-covered",
        gss_code=f"{SYNTHETIC_GSS_PREFIX}000200",
        region=Region.LONDON,
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
        name="Synthetic Empty",
        slug="synthetic-empty",
        gss_code=f"{SYNTHETIC_GSS_PREFIX}000300",
        region=Region.LONDON,
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
        region=Region.LONDON,
    )
    CouncilCoverage.objects.create(council=council)

    assert council not in councils_missing_coverage()


@pytest.mark.django_db
def test_seeded_councils_default_to_london_region():
    """The 0004 migration backfilled the 32 pre-existing rows with a one-off
    default of Region.LONDON (factually correct for the all-London pilot
    data) rather than leaving them null or an arbitrary placeholder."""
    seeded = Council.objects.filter(gss_code__startswith="E09")
    assert seeded.count() == 32
    assert all(council.region == Region.LONDON for council in seeded)


@pytest.mark.django_db
def test_council_picker_view_renders_region_and_council_names():
    """Checks real structure, not just substring presence -- a loose
    substring-only assertion here would have passed even against the
    broken build where a malformed multi-line `{# #}` Django comment leaked
    raw text onto the page (caught only by manual browser testing)."""
    client = Client()
    response = client.get(reverse("council-picker"))

    assert response.status_code == 200
    content = response.content.decode()
    haringey_url = reverse("council-detail", kwargs={"slug": "haringey"})
    js_sri = "sha384-1OflYz7DmKfj0jIJ8DiQC510AbUslTNMYmhRucfm1Eg057frmHHYejk7+YJZZCwX"
    css_sri = "sha384-tm2lkBj7LRznflL/jGlXy/p8q+F2u49L5GXWaZZj2FlYy97QB8SUbC4yVGVz2PQc"

    assert "<summary>London</summary>" in content
    assert f'<a href="{haringey_url}">Haringey</a>' in content
    assert '<div id="council-search-container"' in content
    assert '<p id="search-status">' in content
    # CDN assets must carry the SRI integrity attribute, not be included bare.
    assert f'integrity="{js_sri}"' in content
    assert f'integrity="{css_sri}"' in content
    # No stray/leaked Django comment syntax anywhere in the rendered output.
    assert "{#" not in content and "#}" not in content


@pytest.mark.django_db
def test_council_detail_route_renders_map_for_known_council():
    """ "/" and "/council/<slug>/" are the same screen (sidebar + map), just
    with a council loaded or not -- this checks the loaded state renders
    the map with that council's boundary and highlights it in the sidebar."""
    client = Client()
    url = reverse("council-detail", kwargs={"slug": "haringey"})
    assert url == "/council/haringey/"

    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()
    assert 'id="map"' in content
    assert "haringey.geojson" in content
    assert f'<a href="{url}" aria-current="page">Haringey</a>' in content


@pytest.mark.django_db
def test_council_detail_route_404s_for_unknown_slug():
    client = Client()
    response = client.get(reverse("council-detail", kwargs={"slug": "not-a-real-council"}))
    assert response.status_code == 404


@pytest.mark.django_db
def test_council_picker_root_has_no_council_selected():
    """The "/" state of the shared screen: map has no boundary to fetch yet,
    and no sidebar link is marked as the current one."""
    client = Client()
    response = client.get(reverse("council-picker"))

    assert response.status_code == 200
    content = response.content.decode()
    assert 'data-geojson-url=""' in content
    # The CSS rule `a[aria-current="page"]` in <style> also contains this
    # substring -- check for the attribute as it'd appear on a rendered
    # anchor (leading space), not the bare string.
    assert ' aria-current="page"' not in content
