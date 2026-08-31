from django.http import HttpResponse
from django.shortcuts import render
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


def council_picker(request):
    """GET / — search-first typeahead plus a collapsed-by-default,
    region-grouped browse list. Both are independent entry points into the
    same council list (search bypasses the region hierarchy, it isn't
    filtering within it).

    Region groups are server-rendered straight from the DB via `{% regroup %}`
    so they're always fresh -- the search widget's data comes from the
    separately-generated `council-index.json` instead (see
    `generate_council_index` management command), not this queryset.
    """
    councils = get_councils().filter(is_active=True).order_by("region", "name")
    return render(request, "councils/picker.html", {"councils": councils})


def council_detail_stub(request, slug):
    """Placeholder for the not-yet-built Phase 7 council detail view.

    Exists only so `{% url 'council-detail' %}` resolves for the picker
    page's links -- no real functionality here yet.
    """
    return HttpResponse(f"Coming soon — Phase 7 ({slug})", status=501)
