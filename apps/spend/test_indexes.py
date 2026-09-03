"""EXPLAIN ANALYZE checks that spend/selectors.py's hot-path queries hit an
index rather than scanning the whole table -- see TODO.md's Phase 4 verify
step. Needs enough rows for the planner to prefer an index over a seq scan,
and a fresh ANALYZE since bulk_create in the test transaction doesn't get
picked up by autovacuum before the planner runs.
"""

from datetime import date, timedelta

import pytest
from django.db import connection

from apps.councils.models import Council
from apps.spend.models import SpendTransaction
from apps.spend.selectors import get_council_transactions

ROW_COUNT = 100000


@pytest.fixture
def council():
    return Council.objects.get(slug="haringey")


@pytest.fixture
def bulk_rows(council):
    start = date(2020, 1, 1)
    SpendTransaction.objects.bulk_create(
        SpendTransaction(
            council=council,
            date=start + timedelta(days=i % 2000),
            beneficiary_name=f"Consulting Partner {i:05d}" if i % 1000 == 0 else f"Vendor {i:05d}",
            amount_gbp="123.45",
        )
        for i in range(ROW_COUNT)
    )
    with connection.cursor() as cursor:
        cursor.execute("ANALYZE spend_spendtransaction;")


def _explain(queryset):
    sql, params = queryset.query.sql_with_params()
    with connection.cursor() as cursor:
        cursor.execute(f"EXPLAIN ANALYZE {sql}", params)
        return "\n".join(row[0] for row in cursor.fetchall())


@pytest.mark.django_db
def test_hot_path_queries_use_an_index_not_a_seq_scan(council, bulk_rows):
    # Both checks share the one bulk_rows dataset -- generating 100K rows
    # twice (one fixture instance per test) roughly doubled this file's
    # runtime for no extra coverage.
    date_plan = _explain(
        get_council_transactions(council, date_from=date(2020, 1, 1), date_to=date(2020, 1, 31))
    )
    assert "Seq Scan" not in date_plan, date_plan
    assert "Index Scan" in date_plan or "Bitmap Index Scan" in date_plan, date_plan

    search_plan = _explain(get_council_transactions(council, q="Consulting Partner"))
    assert "Seq Scan" not in search_plan, search_plan
    assert "spend_spendtransaction_beneficiary_name_trgm" in search_plan, search_plan
