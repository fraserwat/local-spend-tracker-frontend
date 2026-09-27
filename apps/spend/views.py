import calendar
from datetime import date
from decimal import Decimal

from django.db.models import Count, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import dateformat
from rest_framework.generics import ListAPIView
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.councils.models import Council

from .forms import TransactionFilterForm
from .pagination import TransactionCursorPagination
from .selectors import (
    SORT_FIELDS,
    get_beneficiary_suggestions,
    get_council_transactions,
    get_latest_transaction_date,
)
from .serializers import SpendTransactionSerializer
from .services.export import stream_transactions_csv
from .throttling import BeneficiaryAutocompleteThrottle, ExportRateThrottle


def _filtered_transactions(council: Council, form: TransactionFilterForm):
    data = form.cleaned_data
    return get_council_transactions(
        council,
        date_from=data.get("date_from"),
        date_to=data.get("date_to"),
        amount_min=data.get("amount_min"),
        amount_max=data.get("amount_max"),
        q=data.get("q") or "",
        category=data.get("category") or None,
        sort=form.sort_field,
        descending=form.descending,
    )


class TransactionListAPIView(ListAPIView):
    """GET /api/v1/councils/<slug>/transactions/ — thin wrapper around spend/selectors.py.

    Reuses TransactionFilterForm for query-param validation so the API and
    the server-rendered view can never disagree on what counts as a valid
    filter -- one place validates, spend/selectors.py is the only place
    that queries.
    """

    serializer_class = SpendTransactionSerializer
    pagination_class = TransactionCursorPagination

    def list(self, request, *args, **kwargs):
        council = get_object_or_404(Council, slug=self.kwargs["slug"])
        form = TransactionFilterForm(request.query_params, council=council)
        if not form.is_valid():
            return Response(form.errors, status=400)
        queryset = _filtered_transactions(council, form)
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data)


class TransactionExportAPIView(APIView):
    """GET /api/v1/councils/<slug>/transactions/export/ — streaming CSV,
    same filters as TransactionListAPIView.

    DRF applies `throttle_classes` before `get()` runs, returning 429
    automatically -- the manual check in council_spend_export_response()
    below exists only because the HTML view isn't a DRF view and has no
    equivalent hook.
    """

    throttle_classes = [ExportRateThrottle]

    def get(self, request, slug):
        council = get_object_or_404(Council, slug=slug)
        form = TransactionFilterForm(request.query_params, council=council)
        if not form.is_valid():
            return Response(form.errors, status=400)
        queryset = _filtered_transactions(council, form)
        return stream_transactions_csv(queryset, filename=f"{council.slug}-transactions.csv")


class BeneficiarySuggestionsAPIView(APIView):
    """GET /api/v1/councils/<slug>/transactions/beneficiaries/?q=... —
    autocomplete source for the Recipient filter. Read-only distinct name
    strings, not a serializer -- there's no model instance to represent.
    """

    throttle_classes = [BeneficiaryAutocompleteThrottle]

    def get(self, request, slug):
        council = get_object_or_404(Council, slug=slug)
        q = request.query_params.get("q", "").strip()
        return Response({"results": get_beneficiary_suggestions(council, q)})


def _link_with(request, mutate) -> str:
    """Same-page URL with `mutate` applied to a copy of the current GET
    params, cursor always dropped -- every link builder below changes the
    page's filters/sort, which invalidates whatever pagination cursor was
    in the old URL."""
    params = request.GET.copy()
    mutate(params)
    params.pop("cursor", None)
    return f"?{params.urlencode()}"


def _date_preset_link(request, date_from: date, date_to: date) -> str:
    """Same shape as _sort_link below, but for the two Day/Month/Year
    subfields DayMonthYearField's widget renders as (see forms.py) --
    date_from_0/1/2 for day/month/year, not one date_from param."""

    def mutate(params):
        params["date_from_0"], params["date_from_1"], params["date_from_2"] = (
            str(date_from.day),
            str(date_from.month),
            str(date_from.year),
        )
        params["date_to_0"], params["date_to_1"], params["date_to_2"] = (
            str(date_to.day),
            str(date_to.month),
            str(date_to.year),
        )

    return _link_with(request, mutate)


def _remove_filter_link(request, keys: list[str]) -> str:
    """Same-page URL with the given GET params (and any cursor) dropped --
    what an active-filter chip's remove button links to."""

    def mutate(params):
        for key in keys:
            params.pop(key, None)

    return _link_with(request, mutate)


def _remove_category_link(request, value: str) -> str:
    """Same shape as _remove_filter_link, but drops one value out of the
    repeated `category` param instead of the whole key -- each selected
    category gets its own chip/remove link, not one combined chip."""

    def mutate(params):
        remaining = [v for v in params.getlist("category") if v != value]
        if remaining:
            params.setlist("category", remaining)
        else:
            params.pop("category", None)

    return _link_with(request, mutate)


def _active_filter_chips(request, form: TransactionFilterForm) -> list[dict]:
    """One chip per applied filter, so the active-filter row never has to
    duplicate the parsing TransactionFilterForm already did."""
    cleaned = form.cleaned_data
    chips = []

    date_from, date_to = cleaned.get("date_from"), cleaned.get("date_to")
    # isinstance, not truthy checks -- cleaned_data is typed Any, so mypy
    # can't otherwise narrow it to date (required by dateformat.format)
    # even though DayMonthYearField.compress guarantees date-or-None here.
    # Each branch tests the value it actually formats (rather than a bare
    # `else`) so mypy narrows both, not just the first.
    date_label = None
    if isinstance(date_from, date) and isinstance(date_to, date):
        date_label = (
            f"{dateformat.format(date_from, 'j M Y')} – {dateformat.format(date_to, 'j M Y')}"
        )
    elif isinstance(date_from, date):
        date_label = f"From {dateformat.format(date_from, 'j M Y')}"
    elif isinstance(date_to, date):
        date_label = f"Until {dateformat.format(date_to, 'j M Y')}"
    if date_label:
        date_keys = [f"date_{side}_{i}" for side in ("from", "to") for i in range(3)]
        chips.append({"label": date_label, "remove_link": _remove_filter_link(request, date_keys)})

    amount_min, amount_max = cleaned.get("amount_min"), cleaned.get("amount_max")
    if amount_min is not None or amount_max is not None:
        if amount_min is not None and amount_max is not None:
            label = f"£{amount_min:g} – £{amount_max:g}"
        elif amount_min is not None:
            label = f"Min £{amount_min:g}"
        else:
            label = f"Max £{amount_max:g}"
        chips.append(
            {
                "label": label,
                "remove_link": _remove_filter_link(request, ["amount_min", "amount_max"]),
            }
        )

    q = cleaned.get("q")
    if q:
        chips.append(
            {"label": f'Recipient: "{q}"', "remove_link": _remove_filter_link(request, ["q"])}
        )

    for category in cleaned.get("category") or []:
        chips.append(
            {
                "label": f"Category: {category}",
                "remove_link": _remove_category_link(request, category),
            }
        )

    return chips


def _sort_link(request, field: str, current_sort: str, current_descending: bool) -> str:
    """Build a same-page URL that sorts by `field`, toggling direction if it's
    already the active sort column. Drops any pagination cursor -- changing
    sort order invalidates the caller's position in the old ordering."""

    def mutate(params):
        params["sort"] = field
        params["dir"] = "asc" if (field == current_sort and current_descending) else "desc"

    return _link_with(request, mutate)


def council_spend_view(request, slug):
    """GET /council/<slug>/spend/ — server-rendered sortable/filterable transaction table.
    GET .../spend/?export=csv — same filters, streams a CSV attachment instead
    of rendering the table (one route, not a separate export page -- see
    TransactionExportAPIView for the equivalent API action).

    Calls spend/selectors.py directly (no self-referential HTTP hop to the
    API) for the initial page load; reuses the same TransactionCursorPagination
    the API uses by wrapping the Django request in a DRF Request, so paging
    behaves identically either way.
    """
    council = get_object_or_404(Council, slug=slug)
    form = TransactionFilterForm(request.GET, council=council)
    valid = form.is_valid()

    if valid and request.GET.get("export") == "csv":
        if not ExportRateThrottle().allow_request(Request(request), view=None):
            return HttpResponse("Too many export requests, try again shortly.", status=429)
        queryset = _filtered_transactions(council, form)
        return stream_transactions_csv(queryset, filename=f"{council.slug}-transactions.csv")

    page = []
    total_count = 0
    total_amount = Decimal("0")
    paginator = TransactionCursorPagination()
    if valid:
        queryset = _filtered_transactions(council, form)
        page = paginator.paginate_queryset(queryset, Request(request)) or []
        # One aggregate query over the filtered (unsliced) queryset -- an
        # index-backed scan of the matching rows, not the 400K+-row table,
        # so it doesn't reintroduce the offset-pagination cost this view's
        # keyset pagination (see pagination.py) is built to avoid.
        totals = queryset.aggregate(count=Count("id"), amount=Sum("amount_gbp"))
        total_count = totals["count"] or 0
        total_amount = totals["amount"] or Decimal("0")

    current_sort = form.sort_field if valid else "date"
    current_descending = form.descending if valid else True

    preset_links = {}
    latest_date = get_latest_transaction_date(council)
    if latest_date:
        month_start = latest_date.replace(day=1)
        month_end = latest_date.replace(
            day=calendar.monthrange(latest_date.year, latest_date.month)[1]
        )
        year_start = latest_date.replace(month=1, day=1)
        year_end = latest_date.replace(month=12, day=31)
        preset_links = {
            "latest_month": _date_preset_link(request, month_start, month_end),
            "latest_year": _date_preset_link(request, year_start, year_end),
        }

    # Expand the Custom date fields by default once a caller has actually
    # entered one -- otherwise a typed range only the URL remembers looks
    # like it silently vanished behind the collapsed <details>.
    custom_date_open = any(
        request.GET.get(f"date_{side}_{i}") for side in ("from", "to") for i in range(3)
    )

    context = {
        "council": council,
        "form": form,
        "transactions": page,
        "total_count": total_count,
        "total_amount": total_amount,
        "next_link": paginator.get_next_link() if valid else None,
        "previous_link": paginator.get_previous_link() if valid else None,
        "sort": current_sort,
        "dir": "asc" if not current_descending else "desc",
        "sort_links": {
            field: _sort_link(request, field, current_sort, current_descending)
            for field in SORT_FIELDS
        },
        "preset_links": preset_links,
        "custom_date_open": custom_date_open,
        "active_filters": _active_filter_chips(request, form) if valid else [],
        "cluster_active": {
            "date": bool(
                valid and (form.cleaned_data.get("date_from") or form.cleaned_data.get("date_to"))
            ),
            "amount": bool(
                valid
                and (
                    form.cleaned_data.get("amount_min") is not None
                    or form.cleaned_data.get("amount_max") is not None
                )
            ),
            "recipient": bool(valid and form.cleaned_data.get("q")),
            "category": bool(valid and form.cleaned_data.get("category")),
        },
    }
    return render(request, "spend/transactions.html", context)
