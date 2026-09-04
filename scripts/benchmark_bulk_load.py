#!/usr/bin/env python
"""Benchmark bulk_create(batch_size=5000) vs. COPY-staging + INSERT...SELECT
for loading one council's curated parquet into SpendTransaction.

Informs the open benchmark note in docs/ARCHITECTURE.md's ETL loader
section -- run against a real large council's parquet (Croydon, ~1.05M
rows, is the confirmed largest) before deciding whether to change the
production write path in apps/spend/services/etl.py.

Usage:
    uv run python scripts/benchmark_bulk_load.py <path-to-parquet>

Runs against a scratch Council (deleted afterward, cascades clean up
SpendTransaction/DataLoadRun/CouncilCoverage) so it never touches real
data. Both paths pay the same pg_try_advisory_xact_lock + delete-then-insert
transactional overhead, so the comparison isolates the row-insertion
mechanism itself.
"""

import argparse
import io
import os
import sys
import time
from pathlib import Path

import django
import polars as pl

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
django.setup()

from django.db import connection, transaction  # noqa: E402

from apps.councils.models import Council, Region  # noqa: E402
from apps.spend.models import AMOUNT_DECIMAL_PLACES, SpendTransaction  # noqa: E402
from apps.spend.services.etl import load_council_spend  # noqa: E402

SCRATCH_SLUG = "benchmark-scratch"
STAGING_TABLE = "staging_spend_transaction"


def _make_scratch_council() -> Council:
    Council.objects.filter(slug=SCRATCH_SLUG).delete()
    return Council.objects.create(
        name="Benchmark Scratch",
        slug=SCRATCH_SLUG,
        gss_code="E00000000",
        region=Region.LONDON,
    )


def _relabel_parquet(parquet_path: Path, slug_underscored: str) -> Path:
    """etl.py validates COUNCIL_NAME against the council's own slug --
    write a copy with COUNCIL_NAME overwritten to the scratch slug so
    Path A's unmodified load_council_spend() accepts it."""
    df = pl.read_parquet(parquet_path).with_columns(pl.lit(slug_underscored).alias("COUNCIL_NAME"))
    relabeled = parquet_path.parent / f"_benchmark_{parquet_path.name}"
    df.write_parquet(relabeled)
    return relabeled


def benchmark_bulk_create(council: Council, parquet_path: Path) -> tuple[float, int]:
    SpendTransaction.objects.filter(council=council).delete()
    start = time.perf_counter()
    load_council_spend(council, parquet_path)
    elapsed = time.perf_counter() - start
    return elapsed, SpendTransaction.objects.filter(council=council).count()


def benchmark_copy_staging(council: Council, parquet_path: Path) -> tuple[float, int]:
    SpendTransaction.objects.filter(council=council).delete()

    df = pl.read_parquet(parquet_path).with_columns(pl.col("DATE").cast(pl.Date))
    df = df.with_columns(pl.col("AMOUNT_GBP").round(AMOUNT_DECIMAL_PLACES))
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
    ).write_csv(csv_buf, include_header=False)
    csv_buf.seek(0)

    start = time.perf_counter()
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_xact_lock(%s)", [council.id])
            if not cursor.fetchone()[0]:
                raise RuntimeError(f"load already in progress for council_id={council.id}")

            cursor.execute(f"DROP TABLE IF EXISTS {STAGING_TABLE}")
            cursor.execute(
                f"""
                CREATE UNLOGGED TABLE {STAGING_TABLE} (
                    date date,
                    beneficiary_name text,
                    amount_gbp numeric(14,2),
                    directorate text,
                    category text,
                    sub_category text,
                    description text
                )
                """
            )

            raw_conn = connection.connection
            with (
                raw_conn.cursor() as raw_cursor,
                raw_cursor.copy(
                    f"COPY {STAGING_TABLE} "
                    "(date, beneficiary_name, amount_gbp, directorate, category, "
                    "sub_category, description) FROM STDIN WITH (FORMAT csv)"
                ) as copy,
            ):
                copy.write(csv_buf.read())

            cursor.execute("DELETE FROM spend_spendtransaction WHERE council_id = %s", [council.id])
            cursor.execute(
                f"""
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
                FROM {STAGING_TABLE}
                """,
                [council.id],
            )
            cursor.execute(f"DROP TABLE {STAGING_TABLE}")
    elapsed = time.perf_counter() - start
    return elapsed, row_count


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("parquet_path", type=Path)
    args = parser.parse_args()

    council = _make_scratch_council()
    relabeled_path = _relabel_parquet(args.parquet_path, SCRATCH_SLUG.replace("-", "_"))

    try:
        time_a, rows_a = benchmark_bulk_create(council, relabeled_path)
        time_b, rows_b = benchmark_copy_staging(council, relabeled_path)
        assert rows_a == rows_b, f"row count mismatch between paths: {rows_a} vs {rows_b}"

        print(f"{'rows':>12} {'bulk_create (s)':>18} {'COPY-staging (s)':>18} {'ratio':>8}")
        print(f"{rows_a:>12,} {time_a:>18.2f} {time_b:>18.2f} {time_a / time_b:>7.2f}x")
        print(f"bulk_create: {rows_a / time_a:,.0f} rows/sec")
        print(f"COPY-staging: {rows_b / time_b:,.0f} rows/sec")
    finally:
        with connection.cursor() as cursor:
            cursor.execute(f"DROP TABLE IF EXISTS {STAGING_TABLE}")
        council.delete()
        relabeled_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
