"""Single query surface for apps.councils — views/API call these, not the ORM directly."""

from .models import Council


def get_councils():
    """All councils, ordered by name. Backs both the HTML view and the API."""
    return Council.objects.all()


def councils_missing_coverage():
    """Councils with loaded spend transactions but no `CouncilCoverage` row.

    Onboarding used to be one council at a time by hand, so a missing
    coverage row was easy to spot. At ~300-council scale, bulk loads can
    leave this gap silently -- the ETL loader (apps/spend/services/etl.py)
    only writes coverage as part of a successful `load_council_spend` run,
    so any other write path (or a partial/manual load) can skip it.
    """
    return Council.objects.filter(transactions__isnull=False, coverage__isnull=True).distinct()
