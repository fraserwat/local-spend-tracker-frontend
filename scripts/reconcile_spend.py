#!/usr/bin/env python
"""Reconcile loaded SpendTransaction rows against source parquet, per council.

Cross-checks row count and total amount_gbp for every council with a
successful DataLoadRun -- catches drift between what's loaded and what the
source repo currently holds (stale reload, partial load, source file
changed since last load).

Usage:
    uv run python scripts/reconcile_spend.py            # all councils with a successful load
    uv run python scripts/reconcile_spend.py haringey    # one council
"""

import argparse
import os
import sys
from decimal import Decimal
from pathlib import Path

import django
import polars as pl

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
django.setup()

from django.conf import settings  # noqa: E402
from django.db.models import Sum  # noqa: E402

from apps.councils.models import Council  # noqa: E402
from apps.spend.models import DataLoadRun, SpendTransaction  # noqa: E402


def reconcile_one(council: Council, source_dir: Path) -> tuple[bool, str]:
    last_run = council.load_runs.filter(status=DataLoadRun.Status.SUCCESS).first()
    if last_run is None:
        return True, "SKIP -- no successful load"

    source_path = source_dir / f"{council.slug.replace('-', '_')}.parquet"
    if not source_path.exists():
        return False, f"FAIL -- loaded but source file missing: {source_path}"

    df = pl.read_parquet(source_path)
    source_rows = len(df)
    source_total = round(float(df["AMOUNT_GBP"].sum()), 2)

    db_rows = SpendTransaction.objects.filter(council=council).count()
    db_total = SpendTransaction.objects.filter(council=council).aggregate(t=Sum("amount_gbp"))[
        "t"
    ] or Decimal("0")
    db_total = round(float(db_total), 2)

    if db_rows != source_rows or db_total != source_total:
        return False, (
            f"MISMATCH -- db: {db_rows} rows / £{db_total:,.2f}, "
            f"source: {source_rows} rows / £{source_total:,.2f}"
        )
    return True, f"OK -- {db_rows} rows / £{db_total:,.2f}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("slug", nargs="?", help="Single council slug; default is all")
    args = parser.parse_args()

    source_dir = Path(settings.SPEND_SOURCE_DIR)
    councils = (
        [Council.objects.get(slug=args.slug)] if args.slug else Council.objects.order_by("slug")
    )

    all_ok = True
    for council in councils:
        ok, message = reconcile_one(council, source_dir)
        all_ok &= ok
        print(f"{council.slug:25} {message}")

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
