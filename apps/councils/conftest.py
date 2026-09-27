import pytest

from apps.councils.models import Council, Region

# Deliberately out of real ONS range (E09/E06/E07/E08 etc. are all real
# prefixes) so synthetic test councils can never collide with real seeded
# data or be mistaken for one.
SYNTHETIC_GSS_PREFIX = "E99"


@pytest.fixture
def make_synthetic_council():
    def _make(slug: str, gss_suffix: str, **overrides) -> Council:
        defaults = {
            "name": f"Synthetic {slug}",
            "gss_code": f"{SYNTHETIC_GSS_PREFIX}{gss_suffix}",
            "region": Region.LONDON,
        }
        defaults.update(overrides)
        return Council.objects.create(slug=slug, **defaults)

    return _make
