from django.shortcuts import get_object_or_404, render
from rest_framework.generics import ListAPIView
from rest_framework.request import Request
from rest_framework.response import Response

from apps.councils.models import Council

from .forms import TransactionFilterForm
from .pagination import TransactionCursorPagination
from .selectors import SORT_FIELDS, get_council_transactions
from .serializers import SpendTransactionSerializer


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

    Calls spend/selectors.py directly (no self-referential HTTP hop to the
    API) for the initial page load; reuses the same TransactionCursorPagination
    the API uses by wrapping the Django request in a DRF Request, so paging
    behaves identically either way.
    """
    council = get_object_or_404(Council, slug=slug)
    form = TransactionFilterForm(request.GET)

    page = []
    paginator = TransactionCursorPagination()
    if form.is_valid():
        queryset = _filtered_transactions(council, form)
        page = paginator.paginate_queryset(queryset, Request(request)) or []

    current_sort = form.sort_field if form.is_valid() else "date"
    current_descending = form.descending if form.is_valid() else True
    context = {
        "council": council,
        "form": form,
        "transactions": page,
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
