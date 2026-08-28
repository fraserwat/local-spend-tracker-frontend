from rest_framework.generics import ListAPIView
from rest_framework.pagination import CursorPagination

from .selectors import get_councils
from .serializers import CouncilSerializer


class CouncilCursorPagination(CursorPagination):
    # Council has no `created` timestamp (project default ordering is
    # '-created'), so pin ordering to a field that actually exists.
    ordering = "name"


class CouncilListView(ListAPIView):
    """GET /api/v1/councils/ — thin wrapper around councils/selectors.py."""

    serializer_class = CouncilSerializer
    pagination_class = CouncilCursorPagination

    def get_queryset(self):
        return get_councils()
