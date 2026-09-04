import hashlib
import io
import json
from datetime import datetime
from io import StringIO

import boto3
import polars as pl
import pytest
from django.core.management import CommandError, call_command
from moto import mock_aws

from apps.councils.models import Council
from apps.spend.models import DataLoadRun, SpendTransaction
from apps.spend.services import r2

BUCKET = "test-bucket"


@pytest.fixture
def r2_settings(settings):
    settings.R2_ACCOUNT_ID = "test-account"
    settings.R2_ACCESS_KEY_ID = "test-key"
    settings.R2_SECRET_ACCESS_KEY = "test-secret"
    settings.R2_BUCKET = BUCKET


@pytest.fixture
def s3_client(r2_settings, monkeypatch):
    # See apps/spend/test_r2.py for why _client() must be patched to hand
    # back this moto-backed client rather than r2.py's real R2 endpoint.
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET)
        monkeypatch.setattr(r2, "_client", lambda: client)
        yield client


def _curated_parquet_bytes(slug: str, *, row_count: int = 1) -> bytes:
    df = pl.DataFrame(
        [
            {
                "COUNCIL_NAME": slug,
                "DATE": datetime(2026, 1, 15),
                "BENEFICIARY_NAME": "Acme Ltd",
                "AMOUNT_GBP": 100.0,
                "DIRECTORATE": "",
                "CATEGORY": "",
                "SUB_CATEGORY": "",
                "DESCRIPTION": "",
            }
        ]
        * row_count
    )
    buf = io.BytesIO()
    df.write_parquet(buf)
    return buf.getvalue()


def _seed_council(client, slug: str, *, corrupt_parquet: bool = False) -> None:
    parquet_bytes = _curated_parquet_bytes(slug)
    sha256 = hashlib.sha256(parquet_bytes).hexdigest()
    manifest = {
        "schema_version": 1,
        "council": slug,
        "source_run": "nightly",
        "updated_at": "2026-09-04T13:36:06Z",
        "curated": {
            "key": f"curated/{slug}.parquet",
            "row_count": 1,
            "size_bytes": len(parquet_bytes),
            "etag": "irrelevant",
            "sha256": sha256,
        },
    }
    client.put_object(
        Bucket=BUCKET, Key=f"manifest/{slug}.json", Body=json.dumps(manifest).encode()
    )
    if corrupt_parquet:
        parquet_bytes = parquet_bytes + b"\x00corrupt"
    client.put_object(Bucket=BUCKET, Key=f"curated/{slug}.parquet", Body=parquet_bytes)


@pytest.mark.django_db
def test_command_maps_hyphenated_slug_to_underscored_filename(tmp_path):
    # migration 0002 already seeds all 32 London boroughs, Tower Hamlets
    # included -- fetch it rather than creating a duplicate slug.
    council = Council.objects.get(slug="tower-hamlets")
    # Sibling repo's curated filenames use underscores, not hyphens.
    source = tmp_path / "tower_hamlets.parquet"
    pl.DataFrame(
        [
            {
                "COUNCIL_NAME": "tower_hamlets",
                "DATE": datetime(2026, 1, 15),
                "BENEFICIARY_NAME": "Acme Consulting Ltd",
                "AMOUNT_GBP": 100.0,
                "DIRECTORATE": "",
                "CATEGORY": "",
                "SUB_CATEGORY": "",
                "DESCRIPTION": "",
            }
        ]
    ).write_parquet(source)

    call_command(
        "load_council_spend", "tower-hamlets", "--source-dir", str(tmp_path), stdout=StringIO()
    )

    assert SpendTransaction.objects.filter(council=council).count() == 1


@pytest.mark.django_db
def test_command_from_r2_loads_council(s3_client):
    council = Council.objects.get(slug="tower-hamlets")
    _seed_council(s3_client, "tower_hamlets")

    call_command("load_council_spend", "tower-hamlets", "--from-r2", stdout=StringIO())

    assert SpendTransaction.objects.filter(council=council).count() == 1


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
    _seed_council(s3_client, "tower_hamlets")
    out = StringIO()

    call_command("load_council_spend", "tower-hamlets", "--from-r2", "--dry-run", stdout=out)

    assert SpendTransaction.objects.count() == 0
    assert "dry-run OK" in out.getvalue()


@pytest.mark.django_db
def test_command_from_r2_surfaces_sha256_mismatch_as_command_error(s3_client):
    council = Council.objects.get(slug="tower-hamlets")
    _seed_council(s3_client, "tower_hamlets", corrupt_parquet=True)

    with pytest.raises(CommandError, match="tower_hamlets"):
        call_command("load_council_spend", "tower-hamlets", "--from-r2", stdout=StringIO())

    assert DataLoadRun.objects.filter(council=council).count() == 0
