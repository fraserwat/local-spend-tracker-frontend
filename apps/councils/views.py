from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.pagination import CursorPagination

from .models import Council
from .nations import NATIONS
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

    404s (not a null-ish payload) for a not-yet-loaded council, so map.js's
    existing missing-boundary catch-and-degrade handles this too.
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

    Region groups render from the DB directly via `{% regroup %}`; the
    search widget uses the separately-generated `council-index.json`
    instead, not this queryset.
    """
    council = get_object_or_404(Council, slug=slug) if slug else None
    councils = get_councils().filter(is_active=True).order_by("region", "name")
    context = {
        "council": council,
        "councils": councils,
        "selected_slug": slug,
    }
    if council:
        # Not every council has a boundary file yet (Phase 7); those just
        # render an empty map rather than 404ing the page.
        context["geojson_static_path"] = f"councils/geo/{council.slug}.geojson"
        context["coverage_url"] = reverse("council-coverage", kwargs={"slug": council.slug})
    return render(request, "councils/main.html", context)


def nation_dashboard(request, slug):
    """GET /nations/<slug>/ — the map screen with a nation's own info card,
    not a council.

    Scotland/Wales/Northern Ireland have no Council rows (no comparable
    itemised spend data to onboard), so this is a static info screen, not a
    variant of council_dashboard's DB-backed lookup. Its own route means
    the state is shareable/back-button-able instead of only reachable by
    clicking the map's grey nation overlay -- and, critically, gives it a
    real "no council selected" render instead of stacking under whatever
    council happened to be selected before the click (the bug this replaces).
    """
    nation = NATIONS.get(slug)
    if nation is None:
        raise Http404(f"unknown nation slug={slug!r}")
    councils = get_councils().filter(is_active=True).order_by("region", "name")
    context = {
        "council": None,
        "nation": nation,
        "councils": councils,
        "selected_slug": None,
    }
    return render(request, "councils/main.html", context)
