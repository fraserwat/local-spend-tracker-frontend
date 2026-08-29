from django.shortcuts import get_object_or_404
from django.views.generic import TemplateView
from rest_framework.generics import ListAPIView
from rest_framework.pagination import CursorPagination

from .models import Council
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


class MapView(TemplateView):
    """Screen 1, Phase 3 slice: bare Leaflet map, one council's boundary.

    Hardcodes Haringey for now — Phase 7 generalises this to all 32 boroughs
    via the geo manifest built by scripts/fetch_boundaries.py.
    """

    template_name = "councils/map.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["council"] = get_object_or_404(Council, slug="haringey")
        return context
