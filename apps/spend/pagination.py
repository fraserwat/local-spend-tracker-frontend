from rest_framework.pagination import CursorPagination

from .selectors import DEFAULT_SORT, SORT_FIELDS


class TransactionCursorPagination(CursorPagination):
    """Keyset pagination shared by the HTML view and the API.

    Councils run to 400K+ rows (see docs/ARCHITECTURE.md), so offset
    pagination is out -- constant-time keyset lookup regardless of page
    depth. Ordering is derived from the same `sort`/`dir` query params (and
    the same allow-list) that spend/selectors.py uses for filtering, so a
    sort-order link and its paginated results can never disagree.

    Reused as-is by the server-rendered view by wrapping the Django request
    in `rest_framework.request.Request` -- `get_ordering` only reads
    `request.query_params`, so no DRF view/serializer machinery is needed
    for that path.
    """

    page_size = 50
    ordering = (f"-{DEFAULT_SORT}", "-id")

    def get_ordering(self, request, queryset, view):
        sort = request.query_params.get("sort", DEFAULT_SORT)
        field = SORT_FIELDS.get(sort, SORT_FIELDS[DEFAULT_SORT])
        descending = request.query_params.get("dir", "desc") != "asc"
        return (f"-{field}", "-id") if descending else (field, "id")
