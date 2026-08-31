from datetime import date, datetime
from decimal import Decimal

import polars as pl
import psycopg
import pytest
from django.conf import settings

from apps.councils.models import Council, Region
from apps.spend.models import DataLoadRun, SpendTransaction
from apps.spend.services.etl import LoadError, load_council_spend


def _write_parquet(tmp_path, slug, rows):
    path = tmp_path / f"{slug}.parquet"
    pl.DataFrame(rows).write_parquet(path)
    return path


def _row(**overrides):
    row = {
        "COUNCIL_NAME": "testborough",
        "DATE": datetime(2026, 1, 15),
        "BENEFICIARY_NAME": "Acme Consulting Ltd",
        "AMOUNT_GBP": 12345.67,
        "DIRECTORATE": "Finance",
        "CATEGORY": "Fees",
        "SUB_CATEGORY": "Consultant",
        "DESCRIPTION": "Advisory work",
    }
    row.update(overrides)
    return row


@pytest.fixture
def council(db):
    return Council.objects.create(
        name="Test Borough", slug="testborough", gss_code="E09000998", region=Region.LONDON
    )


@pytest.mark.django_db
def test_load_maps_fields_and_backfills_nulls(council, tmp_path):
    source = _write_parquet(
        tmp_path,
        "testborough",
        [_row(), _row(BENEFICIARY_NAME="Beta Ltd", SUB_CATEGORY=None, DESCRIPTION=None)],
    )

    run = load_council_spend(council, source)

    assert run.status == DataLoadRun.Status.SUCCESS
    assert run.row_count == 2
    txn = SpendTransaction.objects.get(beneficiary_name="Beta Ltd")
    assert txn.sub_category == ""
    assert txn.description == ""
    assert txn.amount_gbp == Decimal("12345.67")
    assert txn.date.isoformat() == "2026-01-15"

    coverage = council.coverage
    assert coverage.earliest_transaction_date.isoformat() == "2026-01-15"
    assert coverage.last_loaded_at is not None


@pytest.mark.django_db
def test_load_handles_date_typed_column(council, tmp_path):
    """Upstream DATE column may be pl.Date (no time component) rather than
    pl.Datetime -- both are valid outputs of the harmonise() step."""
    source = _write_parquet(tmp_path, "testborough", [_row(DATE=date(2026, 1, 15))])

    run = load_council_spend(council, source)

    assert run.status == DataLoadRun.Status.SUCCESS
    txn = SpendTransaction.objects.get(council=council)
    assert txn.date.isoformat() == "2026-01-15"

    coverage = council.coverage
    assert coverage.earliest_transaction_date.isoformat() == "2026-01-15"
    assert coverage.latest_transaction_date.isoformat() == "2026-01-15"


@pytest.mark.django_db
def test_load_is_idempotent(council, tmp_path):
    source = _write_parquet(tmp_path, "testborough", [_row(), _row(BENEFICIARY_NAME="Beta Ltd")])

    load_council_spend(council, source)
    load_council_spend(council, source)

    assert SpendTransaction.objects.filter(council=council).count() == 2
    runs = DataLoadRun.objects.filter(council=council).order_by("started_at")
    assert list(runs.values_list("status", flat=True)) == [
        DataLoadRun.Status.SUCCESS,
        DataLoadRun.Status.SUCCESS,
    ]


@pytest.mark.django_db
def test_load_failure_marks_run_failed_and_writes_nothing(council, tmp_path):
    bad_row = _row()
    del bad_row["DESCRIPTION"]
    source = _write_parquet(tmp_path, "testborough", [bad_row])

    with pytest.raises(LoadError, match="missing"):
        load_council_spend(council, source)

    run = DataLoadRun.objects.get(council=council)
    assert run.status == DataLoadRun.Status.FAILED
    assert "missing" in run.error_message
    assert SpendTransaction.objects.filter(council=council).count() == 0


@pytest.mark.django_db
def test_load_rejects_wrong_council_file(council, tmp_path):
    source = _write_parquet(tmp_path, "testborough", [_row(COUNCIL_NAME="othercouncil")])

    with pytest.raises(LoadError, match="COUNCIL_NAME"):
        load_council_spend(council, source)

    assert DataLoadRun.objects.get(council=council).status == DataLoadRun.Status.FAILED


@pytest.mark.django_db(transaction=True)
def test_concurrent_load_rejected(tmp_path):
    council = Council.objects.create(name="Test Borough", slug="testborough", gss_code="E09000998")
    source = _write_parquet(tmp_path, "testborough", [_row()])

    db = settings.DATABASES["default"]
    blocker = psycopg.connect(
        dbname=db["NAME"],
        user=db["USER"],
        password=db["PASSWORD"],
        host=db["HOST"] or "localhost",
        port=db["PORT"] or 5432,
    )
    blocker.autocommit = True
    try:
        with blocker.cursor() as cur:
            cur.execute("SELECT pg_advisory_lock(%s)", [council.id])

        with pytest.raises(LoadError, match="already in progress"):
            load_council_spend(council, source)
    finally:
        with blocker.cursor() as cur:
            cur.execute("SELECT pg_advisory_unlock(%s)", [council.id])
        blocker.close()
