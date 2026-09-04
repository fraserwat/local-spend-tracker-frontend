import pytest
from django.core.management import CommandError, call_command

from apps.councils.management.commands import onboard_english_councils as cmd
from apps.councils.models import Council, Region

HARINGEY_ATTRS = {"LAD25CD": "E09000014", "LAD25NM": "Haringey", "RGN25CD": "E12000007"}
BRISTOL_ATTRS = {
    "LAD25CD": "E06000023",
    "LAD25NM": "Bristol, City of",
    "RGN25CD": "E12000009",
}
FOLKESTONE_ATTRS = {
    "LAD25CD": "E07000112",
    "LAD25NM": "Folkestone and Hythe",
    "RGN25CD": "E12000008",
}


class FakeResponse:
    def __init__(self, features):
        self._payload = {"features": [{"attributes": a} for a in features]}

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _patch_ons(monkeypatch, features):
    monkeypatch.setattr(cmd.requests, "get", lambda *args, **kwargs: FakeResponse(features))


@pytest.mark.django_db
def test_skips_council_already_onboarded(monkeypatch):
    """Haringey is seeded by migration 0002 -- rerunning must not touch it."""
    _patch_ons(monkeypatch, [HARINGEY_ATTRS])
    before = Council.objects.get(gss_code="E09000014")

    call_command("onboard_english_councils")

    after = Council.objects.get(gss_code="E09000014")
    assert before.slug == after.slug
    assert Council.objects.filter(gss_code="E09000014").count() == 1


@pytest.mark.django_db
def test_creates_new_council_with_mapped_region(monkeypatch):
    _patch_ons(monkeypatch, [BRISTOL_ATTRS])

    call_command("onboard_english_councils")

    council = Council.objects.get(gss_code="E06000023")
    assert council.name == "Bristol, City of"
    assert council.region == Region.SOUTH_WEST


@pytest.mark.django_db
def test_applies_slug_override_so_r2_lookup_matches(monkeypatch):
    """Bristol's default slugify would be "bristol-city-of"; R2 publishes
    its curated parquet under "bristol". Without the override,
    reload_from_r2's normalize_slug(council.slug) lookup 404s forever."""
    _patch_ons(monkeypatch, [BRISTOL_ATTRS])

    call_command("onboard_english_councils")

    assert Council.objects.get(gss_code="E06000023").slug == "bristol"


@pytest.mark.django_db
def test_slug_override_drops_and_to_match_r2(monkeypatch):
    _patch_ons(monkeypatch, [FOLKESTONE_ATTRS])

    call_command("onboard_english_councils")

    assert Council.objects.get(gss_code="E07000112").slug == "folkestone-hythe"


@pytest.mark.django_db
def test_dry_run_does_not_write(monkeypatch):
    _patch_ons(monkeypatch, [BRISTOL_ATTRS])

    call_command("onboard_english_councils", dry_run=True)

    assert not Council.objects.filter(gss_code="E06000023").exists()


@pytest.mark.django_db
def test_unrecognised_region_code_raises(monkeypatch):
    bad = {"LAD25CD": "E06000099", "LAD25NM": "Nowhere", "RGN25CD": "E12009999"}
    _patch_ons(monkeypatch, [bad])

    with pytest.raises(CommandError, match="unrecognised region"):
        call_command("onboard_english_councils")

    assert not Council.objects.filter(gss_code="E06000099").exists()


@pytest.mark.django_db
def test_no_features_raises(monkeypatch):
    _patch_ons(monkeypatch, [])

    with pytest.raises(CommandError, match="no features"):
        call_command("onboard_english_councils")
