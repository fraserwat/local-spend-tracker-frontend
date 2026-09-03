"""Streaming CSV export, shared by the Spend View's `?export=csv` and the API's
transactions/export/ action -- one implementation, called from both, so the
ORM-only-queries and never-materialize-the-queryset guarantees hold for
either entry point (see docs/ARCHITECTURE.md's security plan).
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

# Councils run 275K-415K+ rows (docs/ARCHITECTURE.md) -- confirmed live,
# Haringey alone is 275,116 -- so this is a true abuse backstop above every
# known pilot council's real count, not a limit hit in normal operation.
CSV_EXPORT_ROW_CAP = 500_000

CHUNK_SIZE = 2000


class _Echo:
    """File-like object whose .write() returns the string instead of buffering
    it -- lets csv.writer drive a generator, per Django's streaming-CSV
    pattern, instead of building the whole file in memory first."""

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

    Never materializes the queryset: `.iterator(chunk_size=...)` pulls rows
    from the DB in batches, and csv.writer emits one row at a time through
    `_Echo`, so process memory stays flat regardless of row count. Capped
    at CSV_EXPORT_ROW_CAP -- the slice becomes a SQL LIMIT, so the cap is
    enforced by the DB, not by counting rows in Python.
    """
    capped = queryset[:CSV_EXPORT_ROW_CAP]
    writer = csv.writer(_Echo())
    response = StreamingHttpResponse(
        (writer.writerow(row) for row in _csv_rows(capped)),
        content_type="text/csv",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
