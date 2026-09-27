import hashlib
from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from apps.councils.models import Council
from apps.spend.conftest import BUCKET, curated_parquet_bytes, seed_council
from apps.spend.models import DataLoadRun, SpendTransaction


@pytest.mark.django_db
def test_skips_council_not_in_r2(s3_client):
    # migration 0002 seeds all 32 London boroughs; none are seeded in R2
    # here, so every one of them should be a clean skip, not an error.
    out = StringIO()

    call_command("reload_from_r2", "--slug", "haringey", stdout=out)

    assert "SKIPPED (not yet in R2)" in out.getvalue()
    assert DataLoadRun.objects.count() == 0


@pytest.mark.django_db
def test_reloads_when_never_loaded(s3_client):
    council = Council.objects.get(slug="barnet")
    seed_council(s3_client, "barnet")
    sha256 = hashlib.sha256(curated_parquet_bytes("barnet")).hexdigest()
    out = StringIO()

    call_command("reload_from_r2", "--slug", "barnet", stdout=out)

    assert "RELOADED (1 rows)" in out.getvalue()
    assert SpendTransaction.objects.filter(council=council).count() == 1
    run = DataLoadRun.objects.get(council=council)
    assert run.status == DataLoadRun.Status.SUCCESS
    assert run.source_sha256 == sha256


@pytest.mark.django_db
def test_skips_unchanged_sha256(s3_client):
    council = Council.objects.get(slug="barnet")
    seed_council(s3_client, "barnet")
    sha256 = hashlib.sha256(curated_parquet_bytes("barnet")).hexdigest()
    DataLoadRun.objects.create(
        council=council,
        source_file_path="r2://barnet",
        status=DataLoadRun.Status.SUCCESS,
        source_sha256=sha256,
    )
    out = StringIO()

    call_command("reload_from_r2", "--slug", "barnet", stdout=out)

    assert "UNCHANGED" in out.getvalue()
    # Still exactly the one run seeded above -- no reload was triggered.
    assert DataLoadRun.objects.filter(council=council).count() == 1
    assert SpendTransaction.objects.filter(council=council).count() == 0


@pytest.mark.django_db
def test_reloads_when_sha256_differs(s3_client):
    council = Council.objects.get(slug="barnet")
    seed_council(s3_client, "barnet")
    DataLoadRun.objects.create(
        council=council,
        source_file_path="r2://barnet",
        status=DataLoadRun.Status.SUCCESS,
        source_sha256="stale-sha-from-a-previous-version",
    )
    out = StringIO()

    call_command("reload_from_r2", "--slug", "barnet", stdout=out)

    assert "RELOADED (1 rows)" in out.getvalue()
    assert SpendTransaction.objects.filter(council=council).count() == 1
    assert DataLoadRun.objects.filter(council=council).count() == 2


@pytest.mark.django_db
def test_dry_run_makes_no_changes(s3_client):
    seed_council(s3_client, "barnet")
    out = StringIO()

    call_command("reload_from_r2", "--slug", "barnet", "--dry-run", stdout=out)

    assert "WOULD RELOAD" in out.getvalue()
    assert DataLoadRun.objects.count() == 0
    assert SpendTransaction.objects.count() == 0


@pytest.mark.django_db
def test_fetch_failure_writes_failed_dataloadrun_and_continues(s3_client):
    barnet = Council.objects.get(slug="barnet")
    camden = Council.objects.get(slug="camden")
    # barnet: manifest present but not valid JSON -- fails at the cheap
    # fetch_manifest step, before any reload is attempted.
    s3_client.put_object(Bucket=BUCKET, Key="manifest/barnet.json", Body=b"{not valid json")
    seed_council(s3_client, "camden")
    out = StringIO()

    with pytest.raises(CommandError, match="one or more councils failed"):
        call_command("reload_from_r2", stdout=out)

    output = out.getvalue()
    assert "barnet" in output and "FAILED (fetch:" in output
    assert "camden" in output and "RELOADED (1 rows)" in output

    barnet_run = DataLoadRun.objects.get(council=barnet)
    assert barnet_run.status == DataLoadRun.Status.FAILED
    assert barnet_run.source_file_path == "r2://barnet"
    assert "not valid JSON" in barnet_run.error_message

    camden_run = DataLoadRun.objects.get(council=camden)
    assert camden_run.status == DataLoadRun.Status.SUCCESS
    assert SpendTransaction.objects.filter(council=camden).count() == 1


@pytest.mark.django_db
def test_slug_filter_only_processes_one_council(s3_client):
    seed_council(s3_client, "barnet")
    seed_council(s3_client, "camden")
    out = StringIO()

    call_command("reload_from_r2", "--slug", "barnet", stdout=out)

    assert "barnet" in out.getvalue()
    assert "camden" not in out.getvalue()
    assert DataLoadRun.objects.filter(council__slug="camden").count() == 0
