import pytest
from django.core.management import CommandError, call_command
from django.urls import reverse
from rest_framework.test import APIClient

from apps.councils.management.commands.import_council_coverage import COVERAGE_FIXTURE
from apps.councils.models import Council, CouncilCoverage, Region
from apps.councils.selectors import get_coverage


@pytest.mark.django_db
def test_get_coverage_returns_none_for_council_with_no_row(make_synthetic_council):
    council = make_synthetic_council("synthetic-unloaded", "000500")
    assert get_coverage(council) is None


@pytest.mark.django_db
def test_get_coverage_returns_row_when_present(make_synthetic_council):
    council = make_synthetic_council("synthetic-loaded", "000600")
    coverage = CouncilCoverage.objects.create(council=council)
    assert get_coverage(council) == coverage


@pytest.mark.django_db
def test_coverage_api_returns_issue_details(make_synthetic_council):
    council = make_synthetic_council("synthetic-issue", "000700")
    CouncilCoverage.objects.create(
        council=council,
        has_data_quality_issue=True,
        detail_text="123 rows predate coverage start.",
    )

    response = APIClient().get(reverse("council-coverage", kwargs={"slug": council.slug}))

    assert response.status_code == 200
    assert response.data["has_data_quality_issue"] is True
    assert response.data["detail_text"] == "123 rows predate coverage start."


@pytest.mark.django_db
def test_coverage_api_returns_no_issue_council(make_synthetic_council):
    council = make_synthetic_council("synthetic-clean", "000800")
    CouncilCoverage.objects.create(council=council)

    response = APIClient().get(reverse("council-coverage", kwargs={"slug": council.slug}))

    assert response.status_code == 200
    assert response.data["has_data_quality_issue"] is False
    assert response.data["detail_text"] == ""


@pytest.mark.django_db
def test_coverage_api_404s_when_council_has_no_coverage_row_yet(make_synthetic_council):
    council = make_synthetic_council("synthetic-no-coverage-row", "000900")

    response = APIClient().get(reverse("council-coverage", kwargs={"slug": council.slug}))

    assert response.status_code == 404


@pytest.mark.django_db
def test_coverage_api_404s_for_unknown_slug():
    response = APIClient().get(reverse("council-coverage", kwargs={"slug": "not-a-council"}))
    assert response.status_code == 404


@pytest.mark.django_db
def test_import_council_coverage_applies_fixture_to_seeded_councils():
    """The 18 London-pilot slugs are seeded by migration 0002; the rest of
    COVERAGE_FIXTURE's nationwide slugs are onboarded live by
    onboard_english_councils, which doesn't run against the test DB, so
    they're created synthetically here. Either way this only needs a
    CouncilCoverage row to exist first, as `load_council_spend` would
    create it, before the fixture can be applied on top."""
    for i, slug in enumerate(COVERAGE_FIXTURE):
        council, _ = Council.objects.get_or_create(
            slug=slug,
            defaults={"name": slug, "gss_code": f"E99{i:06d}", "region": Region.LONDON},
        )
        CouncilCoverage.objects.create(council=council)

    call_command("import_council_coverage")

    redbridge = CouncilCoverage.objects.get(council__slug="redbridge")
    assert redbridge.has_data_quality_issue is True
    assert "1,121" in redbridge.detail_text
    assert "24,679,100" in redbridge.detail_text

    haringey = CouncilCoverage.objects.get(council__slug="haringey")
    assert haringey.has_data_quality_issue is False
    assert haringey.detail_text == ""


@pytest.mark.django_db
def test_import_council_coverage_raises_clear_error_when_row_missing():
    # None of the fixture councils have a CouncilCoverage row yet in this test's DB.
    with pytest.raises(CommandError, match="load_council_spend"):
        call_command("import_council_coverage")
