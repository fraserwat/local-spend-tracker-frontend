"""Parquet -> Postgres loader for one council's spend transactions.

Idempotent full-replace: no transaction ID exists in the upstream schema,
so there's no key to upsert against. Delete+insert runs in one transaction,
giving concurrent readers an old-or-new snapshot (Postgres MVCC) and making
repeat runs converge to the same state rather than accumulating duplicates.
"""

from datetime import datetime
from decimal import Decimal
from itertools import batched
from pathlib import Path
from typing import cast

import polars as pl
from django.db import connection, transaction
from django.utils import timezone

from apps.councils.models import Council, CouncilCoverage
from apps.spend.models import AMOUNT_DECIMAL_PLACES, DataLoadRun, SpendTransaction

# Fixed column contract enforced by the data repo's harmonise() step
# (src/ingest/harmonise.py:TARGET_COLUMNS) -- always exactly these 8
# columns, never fewer or more.
EXPECTED_COLUMNS = {
    "COUNCIL_NAME",
    "DATE",
    "BENEFICIARY_NAME",
    "AMOUNT_GBP",
    "DIRECTORATE",
    "CATEGORY",
    "SUB_CATEGORY",
    "DESCRIPTION",
}

BATCH_SIZE = 5000


class LoadError(Exception):
    """Raised for any failure during a load; DataLoadRun is marked failed first."""


def _validate(df_columns: set[str], council_names: set[str], slug: str) -> None:
    if df_columns != EXPECTED_COLUMNS:
        missing = EXPECTED_COLUMNS - df_columns
        extra = df_columns - EXPECTED_COLUMNS
        raise LoadError(f"column mismatch: missing={missing or None} extra={extra or None}")
    if council_names != {slug}:
        raise LoadError(f"expected COUNCIL_NAME=={{{slug!r}}}, found {council_names}")


def _to_transaction(row: dict, council: Council) -> SpendTransaction:
    amount: float = row["AMOUNT_GBP"]
    date: datetime = row["DATE"]
    return SpendTransaction(
        council=council,
        date=date.date(),
        beneficiary_name=row["BENEFICIARY_NAME"],
        # str() before Decimal avoids binary float artifacts (e.g. 8249.13
        # stored as 8249.129999999999) that Decimal(float) would preserve.
        amount_gbp=Decimal(str(round(amount, AMOUNT_DECIMAL_PLACES))),
        directorate=row["DIRECTORATE"] or "",
        category=row["CATEGORY"] or "",
        sub_category=row["SUB_CATEGORY"] or "",
        description=row["DESCRIPTION"] or "",
    )


def load_council_spend(council: Council, source_path: Path) -> DataLoadRun:
    """Full-replace load of `council`'s SpendTransactions from `source_path`.

    Raises LoadError (or propagates any other exception) on failure, after
    marking the DataLoadRun as failed -- the audit record survives even
    though the payload transaction rolled back.
    """
    run = DataLoadRun.objects.create(council=council, source_file_path=str(source_path))

    try:
        df = pl.read_parquet(source_path)
        _validate(set(df.columns), set(df["COUNCIL_NAME"].unique().to_list()), council.slug)

        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_try_advisory_xact_lock(%s)", [council.id])
                if not cursor.fetchone()[0]:
                    raise LoadError(f"load already in progress for council_id={council.id}")

            SpendTransaction.objects.filter(council=council).delete()

            row_count = 0
            for batch in batched(df.iter_rows(named=True), BATCH_SIZE, strict=False):
                SpendTransaction.objects.bulk_create(_to_transaction(row, council) for row in batch)
                row_count += len(batch)

            dates = df["DATE"]
            earliest = cast(datetime, dates.min())
            latest = cast(datetime, dates.max())
            CouncilCoverage.objects.update_or_create(
                council=council,
                defaults={
                    "earliest_transaction_date": earliest.date(),
                    "latest_transaction_date": latest.date(),
                    "last_loaded_at": timezone.now(),
                },
            )
    except Exception as exc:
        run.status = DataLoadRun.Status.FAILED
        run.error_message = str(exc)
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "error_message", "finished_at"])
        raise

    run.status = DataLoadRun.Status.SUCCESS
    run.row_count = row_count
    run.finished_at = timezone.now()
    run.save(update_fields=["status", "row_count", "finished_at"])
    return run
