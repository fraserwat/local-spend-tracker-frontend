"""Streaming CSV export, shared by the Spend View's `?export=csv` and the
API's transactions/export/ action, so both get the same never-materialize
guarantee.
"""

import csv
from collections.abc import Iterable

from django.db.models import QuerySet
from django.http import StreamingHttpResponse

from apps.spend.models import SpendTransaction

# Matches SpendTransactionSerializer's field order.
CSV_FIELDS = [
    "date",
    "beneficiary_name",
    "amount_gbp",
    "directorate",
    "category",
    "sub_category",
    "description",
]

# Councils run 275K-415K+ rows (Haringey alone is 275,116) -- an abuse
# backstop above every known pilot council, not a normal-operation limit.
CSV_EXPORT_ROW_CAP = 500_000

CHUNK_SIZE = 2000


class _Echo:
    """.write() returns the string instead of buffering it, so csv.writer
    can drive a generator (Django's streaming-CSV pattern)."""

    def write(self, value: str) -> str:
        return value


def _csv_rows(queryset: QuerySet[SpendTransaction]) -> Iterable[list[str]]:
    yield CSV_FIELDS
    for txn in queryset.iterator(chunk_size=CHUNK_SIZE):
        yield [str(getattr(txn, field)) for field in CSV_FIELDS]


def stream_transactions_csv(
    queryset: QuerySet[SpendTransaction], filename: str
) -> StreamingHttpResponse:
    """Stream `queryset` as a CSV attachment.

    Never materializes the queryset -- `.iterator()` batches from the DB,
    `_Echo` emits one row at a time, so memory stays flat. The
    CSV_EXPORT_ROW_CAP slice becomes a SQL LIMIT, enforced by the DB.
    """
    capped = queryset[:CSV_EXPORT_ROW_CAP]
    writer = csv.writer(_Echo())
    response = StreamingHttpResponse(
        (writer.writerow(row) for row in _csv_rows(capped)),
        content_type="text/csv",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
