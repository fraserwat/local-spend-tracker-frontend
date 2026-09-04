"""Read-only R2 client: list published councils, fetch one council's
curated parquet + manifest, verify integrity before handing off to etl.py.

Credentials come from Django settings (R2_ACCOUNT_ID/R2_ACCESS_KEY_ID/
R2_SECRET_ACCESS_KEY/R2_BUCKET), sourced from env via django-environ --
this repo holds a separate, read-only-scoped token, never the sibling
repo's write-scoped publishing credentials.
"""

import hashlib
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from django.conf import settings

# R2 keys published against the hyphen -> underscore convention -- checked
# before the general swap below.
SLUG_OVERRIDES = {
    "isles-of-scilly": "isles-of-scilly",
}


def normalize_slug(slug: str) -> str:
    """Django Council.slug is hyphenated; R2/the sibling repo use
    underscores (e.g. "east-suffolk" -> "east_suffolk"), except for the
    handful of councils in SLUG_OVERRIDES."""
    if slug in SLUG_OVERRIDES:
        return SLUG_OVERRIDES[slug]
    return slug.replace("-", "_")


class R2Error(Exception):
    """Raised for any R2 fetch/verify failure: missing config, missing
    object, or a sha256 mismatch between the manifest and the downloaded
    parquet. Never returns a partially-verified result instead."""


@dataclass(frozen=True)
class FetchedCouncil:
    manifest: dict
    parquet_path: Path


def _require_config() -> tuple[str, str, str, str]:
    values = (
        settings.R2_ACCOUNT_ID,
        settings.R2_ACCESS_KEY_ID,
        settings.R2_SECRET_ACCESS_KEY,
        settings.R2_BUCKET,
    )
    if not all(values):
        raise R2Error(
            "R2 settings incomplete: R2_ACCOUNT_ID/R2_ACCESS_KEY_ID/"
            "R2_SECRET_ACCESS_KEY/R2_BUCKET must all be set"
        )
    return values


def _client():
    account_id, access_key, secret_key, _ = _require_config()
    return boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="auto",
        config=Config(signature_version="s3v4"),
    )


def list_councils() -> list[str]:
    """Slugs of every council with a published manifest, via ListObjectsV2
    on the manifest/ prefix -- there is no aggregate index object."""
    _, _, _, bucket = _require_config()
    client = _client()
    slugs: list[str] = []
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix="manifest/"):
        for obj in page.get("Contents", []):
            key = obj["Key"]  # "manifest/{slug}.json"
            if key.endswith(".json"):
                slugs.append(key.removeprefix("manifest/").removesuffix(".json"))
    return sorted(slugs)


def _download_manifest(client, bucket: str, slug: str, dest_dir: Path) -> dict:
    manifest_path = dest_dir / f"{slug}.manifest.json"

    try:
        client.download_file(bucket, f"manifest/{slug}.json", str(manifest_path))
    except ClientError as exc:
        raise R2Error(f"manifest not found for slug={slug!r}") from exc

    try:
        return json.loads(manifest_path.read_text())
    except json.JSONDecodeError as exc:
        raise R2Error(f"manifest for slug={slug!r} is not valid JSON") from exc


def fetch_manifest(slug: str) -> dict:
    """Download and parse manifest/{slug}.json only -- no parquet download,
    no sha256 verification (there's nothing downloaded yet to verify).

    Cheap enough to call once per council on every diff check; use
    fetch_council() when the data itself is actually needed.
    """
    _, _, _, bucket = _require_config()
    client = _client()
    with tempfile.TemporaryDirectory() as tmp_dir:
        return _download_manifest(client, bucket, slug, Path(tmp_dir))


def fetch_council(slug: str, dest_dir: Path) -> FetchedCouncil:
    """Download manifest/{slug}.json and curated/{slug}.parquet into
    dest_dir, verify the parquet's sha256 against the manifest.

    Raises R2Error on any missing object or hash mismatch -- never
    returns a FetchedCouncil pointing at unverified data. dest_dir's
    lifecycle (creation/cleanup) is the caller's responsibility.
    """
    _, _, _, bucket = _require_config()
    client = _client()

    manifest = _download_manifest(client, bucket, slug, dest_dir)

    try:
        expected_sha256 = manifest["curated"]["sha256"]
    except (KeyError, TypeError) as exc:
        raise R2Error(f"manifest for slug={slug!r} missing curated.sha256") from exc

    parquet_path = dest_dir / f"{slug}.parquet"
    try:
        client.download_file(bucket, f"curated/{slug}.parquet", str(parquet_path))
    except ClientError as exc:
        raise R2Error(f"curated parquet not found for slug={slug!r}") from exc

    actual_sha256 = hashlib.sha256(parquet_path.read_bytes()).hexdigest()
    if actual_sha256 != expected_sha256:
        raise R2Error(
            f"sha256 mismatch for slug={slug!r}: "
            f"manifest={expected_sha256} downloaded={actual_sha256}"
        )

    return FetchedCouncil(manifest=manifest, parquet_path=parquet_path)
