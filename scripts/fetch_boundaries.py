#!/usr/bin/env python
"""Fetch + simplify London borough boundaries from ONS Open Geography.

Queries the ONS FeatureServer directly for each council's GSS code (reading
gss_code from apps.councils.models.Council, the single source of truth set
up in migration 0002 — not a second hardcoded list that could drift out of
sync). The FeatureServer reprojects server-side to EPSG:4326, so there is no
shapefile conversion or manual pyproj reprojection step. Output is simplified
for web rendering and written as one GeoJSON file per council plus a
manifest recording the exact ONS product used.

Usage:
    uv run python scripts/fetch_boundaries.py haringey
    uv run python scripts/fetch_boundaries.py            # all active councils
"""

import argparse
import json
import os
import sys
from pathlib import Path

import django
import geopandas as gpd
import requests
import shapely
from shapely.geometry import mapping

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
django.setup()

from apps.councils.models import Council  # noqa: E402

# ONS Open Geography Portal, "Local Authority Districts (May 2025) Boundaries
# UK BGC (V2)" — Generalised (Clipped). Pinned by name, not just URL, so a
# future re-fetch against a newer vintage is a one-line change here, not an
# archaeology exercise.
SOURCE_VINTAGE = "LAD_MAY_2025_UK_BGC_V2"
ONS_FEATURE_SERVER = (
    "https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/"
    f"{SOURCE_VINTAGE}/FeatureServer/0/query"
)
SIMPLIFY_TOLERANCE_DEGREES = 0.0002
# ~11cm at UK latitudes — ONS's source precision (13+ decimal places) is
# sub-nanometer and pure file-size waste for a web map.
COORDINATE_PRECISION_DEGREES = 1e-6

GEO_DIR = BASE_DIR / "apps" / "councils" / "static" / "councils" / "geo"
MANIFEST_PATH = GEO_DIR / "manifest.json"
BUNDLE_FILENAME = "all-councils.geojson"


def fetch_boundary(gss_code: str) -> dict:
    response = requests.get(
        ONS_FEATURE_SERVER,
        params={
            "where": f"LAD25CD='{gss_code}'",
            "outFields": "LAD25CD,LAD25NM",
            "f": "geojson",
            "outSR": 4326,
        },
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("features"):
        raise ValueError(f"no ONS feature found for GSS code {gss_code}")
    return data


def simplify_geometry(raw_geojson: dict, tolerance: float) -> dict:
    gdf = gpd.GeoDataFrame.from_features(raw_geojson["features"], crs="EPSG:4326")
    simplified = gdf.geometry.iloc[0].simplify(tolerance, preserve_topology=True)
    rounded = shapely.set_precision(simplified, grid_size=COORDINATE_PRECISION_DEGREES)
    return mapping(rounded)


def write_council_boundary(council: Council) -> dict:
    raw = fetch_boundary(council.gss_code)
    geometry = simplify_geometry(raw, SIMPLIFY_TOLERANCE_DEGREES)
    feature_collection = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "slug": council.slug,
                    "gss_code": council.gss_code,
                    "name": council.name,
                },
                "geometry": geometry,
            }
        ],
    }
    GEO_DIR.mkdir(parents=True, exist_ok=True)
    out_path = GEO_DIR / f"{council.slug}.geojson"
    out_path.write_text(json.dumps(feature_collection, separators=(",", ":")))
    return {
        "slug": council.slug,
        "gss_code": council.gss_code,
        "name": council.name,
        "file": out_path.name,
        "source": SOURCE_VINTAGE,
        "simplify_tolerance_degrees": SIMPLIFY_TOLERANCE_DEGREES,
    }


def update_manifest(entries: list[dict]) -> dict:
    manifest = {"schema_version": 1, "councils": {}}
    if MANIFEST_PATH.exists():
        manifest = json.loads(MANIFEST_PATH.read_text())
        manifest.setdefault("schema_version", 1)
        manifest.setdefault("councils", {})
    for entry in entries:
        manifest["councils"][entry["slug"]] = entry
    manifest["bundle_file"] = BUNDLE_FILENAME
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def write_bundle(manifest: dict) -> None:
    """Combine every council's boundary into one FeatureCollection for map.js's idle outlines."""
    features = []
    for entry in sorted(manifest["councils"].values(), key=lambda e: e["slug"]):
        council_path = GEO_DIR / entry["file"]
        feature_collection = json.loads(council_path.read_text())
        features.extend(feature_collection["features"])
    bundle = {"type": "FeatureCollection", "features": features}
    (GEO_DIR / BUNDLE_FILENAME).write_text(json.dumps(bundle, separators=(",", ":")))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "slugs", nargs="*", help="Council slugs to fetch (default: all active councils)"
    )
    args = parser.parse_args()

    councils = list(
        Council.objects.filter(slug__in=args.slugs)
        if args.slugs
        else Council.objects.filter(is_active=True)
    )
    if args.slugs and len(councils) != len(set(args.slugs)):
        missing = set(args.slugs) - {c.slug for c in councils}
        raise SystemExit(f"no Council found for slug(s): {', '.join(sorted(missing))}")

    entries = [write_council_boundary(council) for council in councils]
    manifest = update_manifest(entries)
    write_bundle(manifest)
    for entry in entries:
        print(f"wrote {entry['file']} ({entry['name']}, {entry['gss_code']})")
    print(f"wrote {BUNDLE_FILENAME} ({len(manifest['councils'])} councils bundled)")


if __name__ == "__main__":
    main()
