"""Parquet -> Postgres loader for one council's spend transactions.

Idempotent full-replace: no transaction ID exists in the upstream schema,
so there's no key to upsert against. Delete+insert runs in one transaction,
giving concurrent readers an old-or-new snapshot (Postgres MVCC) and making
repeat runs converge to the same state rather than accumulating duplicates.
"""

import io
from datetime import date as date_cls
from pathlib import Path
from typing import cast

import polars as pl
from django.db import connection, transaction
from django.utils import timezone
from psycopg import sql

from apps.councils.models import Council, CouncilCoverage
from apps.spend.models import AMOUNT_DECIMAL_PLACES, DataLoadRun
from apps.spend.services.r2 import normalize_slug

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

STAGING_COLUMNS = (
    "date",
    "beneficiary_name",
    "amount_gbp",
    "directorate",
    "category",
    "sub_category",
    "description",
)


class LoadError(Exception):
    """Raised for any failure during a load; DataLoadRun is marked failed first."""


def _validate(df_columns: set[str], council_names: set[str], expected_council_name: str) -> None:
    if df_columns != EXPECTED_COLUMNS:
        missing = EXPECTED_COLUMNS - df_columns
        extra = df_columns - EXPECTED_COLUMNS
        raise LoadError(f"column mismatch: missing={missing or None} extra={extra or None}")
    if council_names != {expected_council_name}:
        raise LoadError(
            f"expected COUNCIL_NAME=={{{expected_council_name!r}}}, found {council_names}"
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
        # Upstream DATE dtype varies (Date vs Datetime) -- normalize once so
        # downstream code always sees plain datetime.date values.
        df = df.with_columns(pl.col("DATE").cast(pl.Date))
        # Round once here rather than per-row in Python -- write_csv's
        # float_precision below then formats every value to exactly this
        # many decimal places, avoiding the binary float artifacts (e.g.
        # 8249.13 -> 8249.129999999999) a naive float->Decimal conversion
        # would otherwise preserve.
        df = df.with_columns(pl.col("AMOUNT_GBP").round(AMOUNT_DECIMAL_PLACES))
        # Source repo's COUNCIL_NAME/filenames use underscores; Django's
        # slugify produces hyphens for multi-word councils (e.g.
        # tower-hamlets vs tower_hamlets) -- normalize before comparing.
        _validate(
            set(df.columns),
            set(df["COUNCIL_NAME"].unique().to_list()),
            normalize_slug(council.slug),
        )

        row_count = len(df)
        csv_buf = io.StringIO()
        df.select(
            [
                "DATE",
                "BENEFICIARY_NAME",
                "AMOUNT_GBP",
                "DIRECTORATE",
                "CATEGORY",
                "SUB_CATEGORY",
                "DESCRIPTION",
            ]
        ).write_csv(csv_buf, include_header=False, float_precision=AMOUNT_DECIMAL_PLACES)
        csv_buf.seek(0)

        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_try_advisory_xact_lock(%s)", [council.id])
                if not cursor.fetchone()[0]:
                    raise LoadError(f"load already in progress for council_id={council.id}")

                # Council-scoped staging table name: reload_from_r2 runs
                # councils sequentially today, but this avoids a collision
                # footgun if that ever changes. sql.Identifier (not an
                # f-string) so the table name is always safely quoted, not
                # string-interpolated into the query.
                staging_table = sql.Identifier(f"staging_spend_transaction_{council.id}")
                cursor.execute(sql.SQL("DROP TABLE IF EXISTS {}").format(staging_table))
                cursor.execute(
                    sql.SQL(
                        """
                        CREATE UNLOGGED TABLE {} (
                            date date,
                            beneficiary_name text,
                            amount_gbp numeric(14,2),
                            directorate text,
                            category text,
                            sub_category text,
                            description text
                        )
                        """
                    ).format(staging_table)
                )

                raw_conn = connection.connection
                copy_stmt = sql.SQL("COPY {} ({}) FROM STDIN WITH (FORMAT csv)").format(
                    staging_table,
                    sql.SQL(", ").join(sql.Identifier(col) for col in STAGING_COLUMNS),
                )
                with (
                    raw_conn.cursor() as raw_cursor,
                    raw_cursor.copy(copy_stmt) as copy,
                ):
                    copy.write(csv_buf.read())

                cursor.execute(
                    "DELETE FROM spend_spendtransaction WHERE council_id = %s", [council.id]
                )
                cursor.execute(
                    sql.SQL(
                        """
                        INSERT INTO spend_spendtransaction
                            (council_id, date, beneficiary_name, amount_gbp,
                             directorate, category, sub_category, description)
                        SELECT %s, date,
                               COALESCE(beneficiary_name, ''),
                               amount_gbp,
                               COALESCE(directorate, ''),
                               COALESCE(category, ''),
                               COALESCE(sub_category, ''),
                               COALESCE(description, '')
                        FROM {}
                        """
                    ).format(staging_table),
                    [council.id],
                )
                cursor.execute(sql.SQL("DROP TABLE {}").format(staging_table))

            dates = df["DATE"]
            CouncilCoverage.objects.update_or_create(
                council=council,
                defaults={
                    "earliest_transaction_date": cast(date_cls, dates.min()),
                    "latest_transaction_date": cast(date_cls, dates.max()),
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
