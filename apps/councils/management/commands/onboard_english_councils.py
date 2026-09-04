"""Bulk-onboard every English local authority district as Council reference
data (GSS code, name, region), sourced live from ONS Open Geography.

Replaces the one-borough-at-a-time pattern (migration 0002_load_london_boroughs)
for anything past the 32-borough London pilot -- that migration hardcodes its
list inline, which doesn't scale to England's ~296 districts/unitaries.
Idempotent: existing Council rows (matched by gss_code) are left untouched.

This command only creates reference rows. It does not fetch boundaries (run
scripts/fetch_boundaries.py afterwards) or load spend data (reload_from_r2
picks up a council automatically, unmodified, once the sibling repo
publishes its curated parquet -- no action needed here for that).
"""

import requests
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from apps.councils.models import Council, Region

# ONS Open Geography Portal, "Local Authority District to Region (April 2025)
# Lookup in EN (V2)" -- one row per English LAD with both the GSS code
# scripts/fetch_boundaries.py joins boundaries on and the ONS region Council
# needs. Same ArcGIS org (ESMARspQHYMw9BZ9) as the boundary FeatureServer
# already pinned there. Pinned by name so a future re-fetch against a newer
# vintage is a one-line change, not archaeology.
SOURCE_VINTAGE = "LAD25_RGN25_EN_LU_v2"
ONS_FEATURE_SERVER = (
    "https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/"
    f"{SOURCE_VINTAGE}/FeatureServer/0/query"
)

# The 9 ONS/ITL1 region codes -- fixed, stable since 2011 census geography.
# Mapped explicitly rather than string-matching RGN25NM, whose casing
# ("Yorkshire and The Humber") doesn't match Region's label exactly.
REGION_BY_CODE = {
    "E12000001": Region.NORTH_EAST,
    "E12000002": Region.NORTH_WEST,
    "E12000003": Region.YORKSHIRE_HUMBER,
    "E12000004": Region.EAST_MIDLANDS,
    "E12000005": Region.WEST_MIDLANDS,
    "E12000006": Region.EAST_OF_ENGLAND,
    "E12000007": Region.LONDON,
    "E12000008": Region.SOUTH_EAST,
    "E12000009": Region.SOUTH_WEST,
}

# Councils where the sibling repo's R2 slug diverges from
# normalize_slug(slugify(ONS name)) by more than the usual hyphen<->underscore
# swap apps.spend.services.r2.normalize_slug() handles -- set explicitly here
# so reload_from_r2 finds their data without a loader change.
SLUG_OVERRIDES = {
    "E06000010": "kingston-upon-hull",  # ONS: "Kingston upon Hull, City of"
    "E06000019": "herefordshire",  # ONS: "Herefordshire, County of"
    "E06000023": "bristol",  # ONS: "Bristol, City of"
    "E06000047": "durham",  # ONS: "County Durham"
    "E06000058": "bournemouth-christchurch-poole",  # R2 slug drops "and"
    "E07000112": "folkestone-hythe",  # R2 slug drops "and"
}


class Command(BaseCommand):
    help = (
        "Bulk-onboard every English local authority district (~296) as "
        "Council reference data, sourced live from ONS Open Geography. "
        "Idempotent -- councils already present (matched by gss_code) are skipped."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be created without writing to the database.",
        )

    def handle(self, dry_run, **options):
        features = self._fetch_lad_region_rows()

        existing_codes = set(Council.objects.values_list("gss_code", flat=True))

        to_create = []
        for attrs in features:
            gss_code = attrs["LAD25CD"]
            if gss_code in existing_codes:
                continue

            region = REGION_BY_CODE.get(attrs["RGN25CD"])
            if region is None:
                raise CommandError(
                    f"{attrs['LAD25NM']} ({gss_code}) has unrecognised region "
                    f"code {attrs['RGN25CD']!r} -- not one of the 9 ONS regions"
                )

            name = attrs["LAD25NM"]
            slug = SLUG_OVERRIDES.get(gss_code, slugify(name))
            council = Council(name=name, slug=slug, gss_code=gss_code, region=region)
            council.full_clean()
            to_create.append(council)

        if dry_run:
            self.stdout.write(
                f"would create {len(to_create)} councils ({len(existing_codes)} already onboarded)"
            )
            return

        with transaction.atomic():
            Council.objects.bulk_create(to_create)

        self.stdout.write(
            self.style.SUCCESS(
                f"created {len(to_create)} councils "
                f"({len(existing_codes)} already onboarded, "
                f"{len(existing_codes) + len(to_create)} total)"
            )
        )

    def _fetch_lad_region_rows(self) -> list[dict]:
        response = requests.get(
            ONS_FEATURE_SERVER,
            params={
                "where": "1=1",
                "outFields": "LAD25CD,LAD25NM,RGN25CD",
                "f": "json",
                "resultRecordCount": "2000",
            },
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        if data.get("exceededTransferLimit"):
            raise CommandError(
                "ONS response exceeded the transfer limit -- paginate with resultOffset"
            )
        features = data.get("features", [])
        if not features:
            raise CommandError("ONS returned no features -- check the service is reachable")
        return [feature["attributes"] for feature in features]
