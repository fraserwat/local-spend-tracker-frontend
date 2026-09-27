"""Single query surface for apps.spend — views/API call these, not the ORM directly."""

import re
from datetime import date
from decimal import Decimal

from django.db.models import Max, QuerySet

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
    category: list[str] | None = None,
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
    if category:
        qs = qs.filter(category__in=category)

    field = SORT_FIELDS.get(sort, SORT_FIELDS[DEFAULT_SORT])
    ordering = (field, "id") if not descending else (f"-{field}", "-id")
    return qs.order_by(*ordering)


def get_latest_transaction_date(council: Council) -> date | None:
    """Most recent transaction date on record for this council, unfiltered
    -- the basis for the "Latest month"/"Latest year" filter presets.
    Deliberately not the current filtered queryset's max: a preset should
    mean the same date range regardless of what else is already applied.
    """
    return SpendTransaction.objects.filter(council=council).aggregate(latest=Max("date"))["latest"]


def get_distinct_categories(council: Council) -> list[str]:
    """Distinct non-blank `category` strings on record for this council, for
    the Category filter's choices. Unfiltered by any other applied filter --
    same "always the full set" rule as get_latest_transaction_date, so
    picking a category doesn't shrink the list of other categories you
    could still add.
    """
    qs = (
        SpendTransaction.objects.filter(council=council)
        .exclude(category="")
        .values_list("category", flat=True)
        .distinct()
        .order_by("category")
    )
    return list(qs)


def get_beneficiary_suggestions(council: Council, q: str, limit: int = 7) -> list[str]:
    """Distinct beneficiary names for this council matching `q`, for the
    Recipient filter's autocomplete. Same iregex path as the main search
    filter above (rewards the beneficiary_name trigram index) -- callers
    should not call this below a couple characters, since an unanchored
    regex with no meaningful prefix does a much bigger scan on a
    400K+-row council.
    """
    if len(q) < 2:
        return []
    qs = (
        SpendTransaction.objects.filter(council=council, beneficiary_name__iregex=re.escape(q))
        .values_list("beneficiary_name", flat=True)
        .distinct()
        .order_by("beneficiary_name")[:limit]
    )
    return list(qs)
