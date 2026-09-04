"""Single query surface for apps.spend — views/API call these, not the ORM directly."""

import re
from datetime import date
from decimal import Decimal

from django.db.models import QuerySet

from apps.councils.models import Council

from .models import SpendTransaction

# Explicit allow-list, never a raw field name into .order_by().
SORT_FIELDS = {
    "date": "date",
    "beneficiary_name": "beneficiary_name",
    "amount_gbp": "amount_gbp",
}
DEFAULT_SORT = "date"


def get_council_transactions(
    council: Council,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    amount_min: Decimal | None = None,
    amount_max: Decimal | None = None,
    q: str = "",
    sort: str = DEFAULT_SORT,
    descending: bool = True,
) -> QuerySet[SpendTransaction]:
    """Filtered, ordered transactions for one council.

    Not sliced — callers keyset-paginate (spend/pagination.py). Invalid
    `sort` values fall back to the default rather than raising, since this
    reads directly from query params. `id` is always the tiebreaker so
    ordering stays total/stable across pages.
    """
    qs = SpendTransaction.objects.filter(council=council)

    if date_from is not None:
        qs = qs.filter(date__gte=date_from)
    if date_to is not None:
        qs = qs.filter(date__lte=date_to)
    if amount_min is not None:
        qs = qs.filter(amount_gbp__gte=amount_min)
    if amount_max is not None:
        qs = qs.filter(amount_gbp__lte=amount_max)
    if q:
        # icontains compiles to UPPER(x) LIKE UPPER(%s), which the trigram
        # GIN index can't use (EXPLAIN: full seq scan). iregex compiles to
        # `~*`, which pg_trgm does index (EXPLAIN: Bitmap Index Scan).
        qs = qs.filter(beneficiary_name__iregex=re.escape(q))

    field = SORT_FIELDS.get(sort, SORT_FIELDS[DEFAULT_SORT])
    ordering = (field, "id") if not descending else (f"-{field}", "-id")
    return qs.order_by(*ordering)
