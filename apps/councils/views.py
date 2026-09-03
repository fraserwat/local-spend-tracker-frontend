from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.pagination import CursorPagination

from .models import Council
from .selectors import get_councils, get_coverage
from .serializers import CouncilSerializer, CoverageSerializer


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


class CouncilCoverageView(RetrieveAPIView):
    """GET /api/v1/councils/<slug>/coverage/ — backs the map's hover badge.

    404s (rather than returning a null-ish payload) when the council exists
    but hasn't been loaded yet, so the frontend's existing missing-boundary
    catch-and-degrade pattern (map.js) handles this the same way.
    """

    serializer_class = CoverageSerializer

    def get_object(self):
        council = get_object_or_404(Council, slug=self.kwargs["slug"])
        coverage = get_coverage(council)
        if coverage is None:
            raise Http404(f"no coverage data loaded yet for council slug={council.slug!r}")
        return coverage


def council_dashboard(request, slug=None):
    """GET / and GET /council/<slug>/ — one screen, two states.

    The sidebar (search + region browse) and the map are the same screen,
    not separate pages: "/" is that screen with no council chosen yet,
    "/council/<slug>/" is the same screen with that council's boundary
    loaded. Selecting a council in the sidebar moves between the two
    without ever leaving the screen.

    Region groups are server-rendered straight from the DB via `{% regroup %}`
    so they're always fresh -- the search widget's data comes from the
    separately-generated `council-index.json` instead (see
    `generate_council_index` management command), not this queryset.
    """
    council = get_object_or_404(Council, slug=slug) if slug else None
    councils = get_councils().filter(is_active=True).order_by("region", "name")
    context = {
        "council": council,
        "councils": councils,
        "selected_slug": slug,
    }
    if council:
        # Only a handful of councils have a fetched boundary file so far
        # (Phase 7 scales this to the rest); other councils just render an
        # empty map until then, rather than 404ing the whole page.
        context["geojson_static_path"] = f"councils/geo/{council.slug}.geojson"
        context["coverage_url"] = reverse("council-coverage", kwargs={"slug": council.slug})
    return render(request, "councils/main.html", context)
