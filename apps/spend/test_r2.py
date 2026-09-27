import json

import pytest

from apps.spend.conftest import BUCKET, curated_parquet_bytes, seed_council
from apps.spend.services import r2


def test_list_councils_returns_sorted_slugs(s3_client):
    seed_council(s3_client, "barnet")
    seed_council(s3_client, "adur")
    # A stray curated/raw object with no matching manifest must not leak in.
    s3_client.put_object(Bucket=BUCKET, Key="curated/orphan.parquet", Body=b"x")

    assert r2.list_councils() == ["adur", "barnet"]


def test_list_councils_raises_r2error_when_config_incomplete(r2_settings, settings):
    settings.R2_BUCKET = ""
    with pytest.raises(r2.R2Error, match="incomplete"):
        r2.list_councils()


def test_fetch_council_downloads_and_verifies_matching_files(s3_client, tmp_path):
    seed_council(s3_client, "barnet")

    fetched = r2.fetch_council("barnet", tmp_path)

    assert fetched.manifest["council"] == "barnet"
    assert fetched.parquet_path.exists()
    assert fetched.parquet_path.read_bytes() == curated_parquet_bytes("barnet")


def test_fetch_council_raises_on_sha256_mismatch(s3_client, tmp_path):
    seed_council(s3_client, "barnet", corrupt_parquet=True)

    with pytest.raises(r2.R2Error, match="sha256 mismatch"):
        r2.fetch_council("barnet", tmp_path)


def test_fetch_council_raises_when_manifest_missing(s3_client, tmp_path):
    with pytest.raises(r2.R2Error, match="manifest fetch failed"):
        r2.fetch_council("nonexistent", tmp_path)


def test_fetch_council_raises_when_parquet_missing(s3_client, tmp_path):
    manifest = {
        "schema_version": 1,
        "council": "barnet",
        "curated": {"sha256": "deadbeef"},
    }
    s3_client.put_object(
        Bucket=BUCKET, Key="manifest/barnet.json", Body=json.dumps(manifest).encode()
    )

    with pytest.raises(r2.R2Error, match="curated parquet fetch failed"):
        r2.fetch_council("barnet", tmp_path)


def test_fetch_manifest_returns_parsed_manifest_without_downloading_parquet(s3_client):
    seed_council(s3_client, "barnet")

    manifest = r2.fetch_manifest("barnet")

    assert manifest["council"] == "barnet"
    assert "sha256" in manifest["curated"]
    # No curated/ GET at all -- list_objects_v2 (paginator setup) plus one
    # get_object for the manifest is all fetch_manifest should ever do.
    keys_fetched = [c["Key"] for c in s3_client.list_objects_v2(Bucket=BUCKET)["Contents"]]
    assert "curated/barnet.parquet" in keys_fetched  # seeded, but never touched by fetch_manifest


def test_fetch_manifest_raises_when_manifest_missing(s3_client):
    with pytest.raises(r2.R2Error, match="manifest fetch failed"):
        r2.fetch_manifest("nonexistent")


def test_fetch_manifest_wraps_connection_timeout_as_r2error(s3_client, monkeypatch):
    """A stalled connection raises a BotoCoreError subclass, not ClientError
    -- must still surface as R2Error, or reload_from_r2's per-council
    error handling never catches it and the whole batch crashes instead
    of marking one council failed and continuing."""
    from botocore.exceptions import ConnectTimeoutError

    def _raise_timeout(*args, **kwargs):
        raise ConnectTimeoutError(endpoint_url="https://example.invalid")

    monkeypatch.setattr(s3_client, "download_file", _raise_timeout)

    with pytest.raises(r2.R2Error, match="manifest fetch failed"):
        r2.fetch_manifest("barnet")


def test_fetch_manifest_raises_on_invalid_json(s3_client):
    s3_client.put_object(Bucket=BUCKET, Key="manifest/barnet.json", Body=b"{not valid json")

    with pytest.raises(r2.R2Error, match="not valid JSON"):
        r2.fetch_manifest("barnet")


@pytest.mark.parametrize(
    ("slug", "expected"),
    [
        ("haringey", "haringey"),
        ("tower-hamlets", "tower_hamlets"),
        ("east-suffolk", "east_suffolk"),
        # R2 published this one still hyphenated -- the general swap would
        # produce "isles_of_scilly", which doesn't exist in the bucket.
        ("isles-of-scilly", "isles-of-scilly"),
    ],
)
def test_normalize_slug(slug, expected):
    assert r2.normalize_slug(slug) == expected
