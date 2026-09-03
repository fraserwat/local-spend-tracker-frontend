from decimal import Decimal

from django.db.models import Count, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from rest_framework.generics import ListAPIView
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.councils.models import Council

from .forms import TransactionFilterForm
from .pagination import TransactionCursorPagination
from .selectors import SORT_FIELDS, get_council_transactions
from .serializers import SpendTransactionSerializer
from .services.export import stream_transactions_csv
from .throttling import ExportRateThrottle


def _filtered_transactions(council: Council, form: TransactionFilterForm):
    data = form.cleaned_data
    return get_council_transactions(
        council,
        date_from=data.get("date_from"),
        date_to=data.get("date_to"),
        amount_min=data.get("amount_min"),
        amount_max=data.get("amount_max"),
        q=data.get("q") or "",
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
        form = TransactionFilterForm(request.query_params)
        if not form.is_valid():
            return Response(form.errors, status=400)
        council = get_object_or_404(Council, slug=self.kwargs["slug"])
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
        form = TransactionFilterForm(request.query_params)
        if not form.is_valid():
            return Response(form.errors, status=400)
        council = get_object_or_404(Council, slug=slug)
        queryset = _filtered_transactions(council, form)
        return stream_transactions_csv(queryset, filename=f"{council.slug}-transactions.csv")


def _sort_link(request, field: str, current_sort: str, current_descending: bool) -> str:
    """Build a same-page URL that sorts by `field`, toggling direction if it's
    already the active sort column. Drops any pagination cursor -- changing
    sort order invalidates the caller's position in the old ordering."""
    params = request.GET.copy()
    params["sort"] = field
    params["dir"] = "asc" if (field == current_sort and current_descending) else "desc"
    params.pop("cursor", None)
    return f"?{params.urlencode()}"


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
    form = TransactionFilterForm(request.GET)

    if form.is_valid() and request.GET.get("export") == "csv":
        if not ExportRateThrottle().allow_request(Request(request), view=None):
            return HttpResponse("Too many export requests, try again shortly.", status=429)
        queryset = _filtered_transactions(council, form)
        return stream_transactions_csv(queryset, filename=f"{council.slug}-transactions.csv")

    page = []
    total_count = 0
    total_amount = Decimal("0")
    paginator = TransactionCursorPagination()
    if form.is_valid():
        queryset = _filtered_transactions(council, form)
        page = paginator.paginate_queryset(queryset, Request(request)) or []
        # One aggregate query over the filtered (unsliced) queryset -- an
        # index-backed scan of the matching rows, not the 400K+-row table,
        # so it doesn't reintroduce the offset-pagination cost this view's
        # keyset pagination (see pagination.py) is built to avoid.
        totals = queryset.aggregate(count=Count("id"), amount=Sum("amount_gbp"))
        total_count = totals["count"] or 0
        total_amount = totals["amount"] or Decimal("0")

    current_sort = form.sort_field if form.is_valid() else "date"
    current_descending = form.descending if form.is_valid() else True
    context = {
        "council": council,
        "form": form,
        "transactions": page,
        "total_count": total_count,
        "total_amount": total_amount,
        "next_link": paginator.get_next_link() if form.is_valid() else None,
        "previous_link": paginator.get_previous_link() if form.is_valid() else None,
        "sort": current_sort,
        "dir": "asc" if not current_descending else "desc",
        "sort_links": {
            field: _sort_link(request, field, current_sort, current_descending)
            for field in SORT_FIELDS
        },
    }
    return render(request, "spend/transactions.html", context)
