"""Single query surface for apps.councils — views/API call these, not the ORM directly."""

from django.db.models import Exists, OuterRef

from .models import Council, CouncilCoverage


def get_councils():
    """All councils, ordered by name. Backs both the HTML view and the API."""
    return Council.objects.all()


def get_active_councils_by_region():
    """Active councils, ordered by region then name. Backs the region and nation dashboards."""
    return get_councils().filter(is_active=True).order_by("region", "name")


def get_coverage(council: Council) -> CouncilCoverage | None:
    """This council's coverage row, or None if it hasn't been loaded yet.

    `council.coverage` raises `RelatedObjectDoesNotExist`, an
    `AttributeError` subclass -- `getattr` resolves it to None without a
    try/except.
    """
    return getattr(council, "coverage", None)


def councils_missing_coverage():
    """Councils with loaded spend transactions but no `CouncilCoverage` row.

    Coverage is only written by a successful `load_council_spend` run --
    any other write path can leave this gap silently at scale.
    """
    from apps.spend.models import SpendTransaction

    has_transactions = Exists(SpendTransaction.objects.filter(council=OuterRef("pk")))
    return Council.objects.filter(has_transactions, coverage__isnull=True)
