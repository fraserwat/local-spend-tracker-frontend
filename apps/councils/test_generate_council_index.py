import json

import pytest
from django.core.management import CommandError, call_command

from apps.councils.models import Council, CouncilCoverage, Region


@pytest.mark.django_db
def test_generate_council_index_matches_db_state(tmp_path):
    """Runs the command against a temp output path (never the committed
    static file) and checks the JSON matches the DB exactly: count, slugs,
    regions."""
    output_path = tmp_path / "council-index.json"

    call_command("generate_council_index", output=str(output_path))

    rows = json.loads(output_path.read_text())
    expected = Council.objects.filter(is_active=True).order_by("name")

    assert len(rows) == expected.count()
    assert [row["slug"] for row in rows] == list(expected.values_list("slug", flat=True))
    for row, council in zip(rows, expected, strict=True):
        assert row["name"] == council.name
        assert row["region"] == council.region
        assert row["region_display"] == Region(council.region).label
        assert row["has_coverage"] == hasattr(council, "coverage")


@pytest.mark.django_db
def test_generate_council_index_has_coverage_true_for_council_with_coverage_row(tmp_path):
    council = Council.objects.create(
        name="Covered Test Council",
        slug="covered-test-council",
        gss_code="E99999997",
        region=Region.LONDON,
    )
    CouncilCoverage.objects.create(council=council)
    output_path = tmp_path / "council-index.json"

    call_command("generate_council_index", output=str(output_path))

    rows = json.loads(output_path.read_text())
    row = next(row for row in rows if row["slug"] == "covered-test-council")
    assert row["has_coverage"] is True


@pytest.mark.django_db
def test_generate_council_index_has_coverage_false_for_council_without_coverage_row(tmp_path):
    Council.objects.create(
        name="Uncovered Test Council",
        slug="uncovered-test-council",
        gss_code="E99999996",
        region=Region.LONDON,
    )
    output_path = tmp_path / "council-index.json"

    call_command("generate_council_index", output=str(output_path))

    rows = json.loads(output_path.read_text())
    row = next(row for row in rows if row["slug"] == "uncovered-test-council")
    assert row["has_coverage"] is False


@pytest.mark.django_db
def test_generate_council_index_excludes_inactive_councils(tmp_path):
    Council.objects.create(
        name="Inactive Test Council",
        slug="inactive-test-council",
        gss_code="E99999999",
        region=Region.LONDON,
        is_active=False,
    )
    output_path = tmp_path / "council-index.json"

    call_command("generate_council_index", output=str(output_path))

    rows = json.loads(output_path.read_text())
    slugs = {row["slug"] for row in rows}
    assert "inactive-test-council" not in slugs


@pytest.mark.django_db
def test_generate_council_index_handles_zero_councils_gracefully(tmp_path):
    Council.objects.all().delete()
    output_path = tmp_path / "council-index.json"

    call_command("generate_council_index", output=str(output_path))

    rows = json.loads(output_path.read_text())
    assert rows == []


@pytest.mark.django_db
def test_generate_council_index_refuses_to_shrink_existing_output(tmp_path):
    """A second run against a wrong DB/env (or a bug that under-queries)
    could silently overwrite the committed index with far fewer councils --
    refuse unless the caller explicitly opts in with --force."""
    output_path = tmp_path / "council-index.json"
    call_command("generate_council_index", output=str(output_path))
    full_count = len(json.loads(output_path.read_text()))
    assert full_count > 0

    Council.objects.all().delete()

    with pytest.raises(CommandError, match="refusing to shrink"):
        call_command("generate_council_index", output=str(output_path))

    # The file from the first run must survive the refused second run.
    assert len(json.loads(output_path.read_text())) == full_count


@pytest.mark.django_db
def test_generate_council_index_force_bypasses_shrink_guard(tmp_path):
    output_path = tmp_path / "council-index.json"
    call_command("generate_council_index", output=str(output_path))

    Council.objects.all().delete()
    call_command("generate_council_index", output=str(output_path), force=True)

    assert json.loads(output_path.read_text()) == []


@pytest.mark.django_db
def test_generate_council_index_raises_clear_error_for_invalid_region(tmp_path):
    Council.objects.create(
        name="Bad Region Council",
        slug="bad-region-council",
        gss_code="E99999998",
        region="not_a_real_region",
    )
    output_path = tmp_path / "council-index.json"

    with pytest.raises(CommandError, match="bad-region-council"):
        call_command("generate_council_index", output=str(output_path))
