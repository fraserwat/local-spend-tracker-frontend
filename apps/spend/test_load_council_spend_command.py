import hashlib
from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from apps.councils.models import Council
from apps.spend.conftest import curated_parquet_bytes, seed_council
from apps.spend.models import DataLoadRun, SpendTransaction


@pytest.mark.django_db
def test_command_maps_hyphenated_slug_to_underscored_filename(tmp_path):
    # migration 0002 already seeds all 32 London boroughs, Tower Hamlets
    # included -- fetch it rather than creating a duplicate slug.
    council = Council.objects.get(slug="tower-hamlets")
    # Sibling repo's curated filenames use underscores, not hyphens.
    source = tmp_path / "tower_hamlets.parquet"
    source.write_bytes(curated_parquet_bytes("tower_hamlets"))

    call_command(
        "load_council_spend", "tower-hamlets", "--source-dir", str(tmp_path), stdout=StringIO()
    )

    assert SpendTransaction.objects.filter(council=council).count() == 1


@pytest.mark.django_db
def test_command_from_r2_loads_council(s3_client):
    council = Council.objects.get(slug="tower-hamlets")
    seed_council(s3_client, "tower_hamlets")

    call_command("load_council_spend", "tower-hamlets", "--from-r2", stdout=StringIO())

    assert SpendTransaction.objects.filter(council=council).count() == 1
    run = DataLoadRun.objects.get(council=council)
    assert run.source_sha256 == hashlib.sha256(curated_parquet_bytes("tower_hamlets")).hexdigest()


@pytest.mark.django_db
def test_command_from_r2_and_source_dir_are_mutually_exclusive(tmp_path):
    with pytest.raises(CommandError, match="not allowed with argument"):
        call_command(
            "load_council_spend",
            "tower-hamlets",
            "--from-r2",
            "--source-dir",
            str(tmp_path),
            stdout=StringIO(),
            stderr=StringIO(),
        )


@pytest.mark.django_db
def test_command_from_r2_dry_run_does_not_write(s3_client):
    seed_council(s3_client, "tower_hamlets")
    out = StringIO()

    call_command("load_council_spend", "tower-hamlets", "--from-r2", "--dry-run", stdout=out)

    assert SpendTransaction.objects.count() == 0
    assert "dry-run OK" in out.getvalue()


@pytest.mark.django_db
def test_command_from_r2_surfaces_sha256_mismatch_as_command_error(s3_client):
    council = Council.objects.get(slug="tower-hamlets")
    seed_council(s3_client, "tower_hamlets", corrupt_parquet=True)

    with pytest.raises(CommandError, match="tower_hamlets"):
        call_command("load_council_spend", "tower-hamlets", "--from-r2", stdout=StringIO())

    assert DataLoadRun.objects.filter(council=council).count() == 0
