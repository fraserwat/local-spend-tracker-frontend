"""Single query surface for apps.councils — views/API call these, not the ORM directly."""

from .models import Council


def get_councils():
    """All councils, ordered by name. Backs both the HTML view and the API."""
    return Council.objects.all()
