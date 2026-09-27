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
    with pytest.raises(r2.R2Error, match="manifest not found"):
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

    with pytest.raises(r2.R2Error, match="curated parquet not found"):
        r2.fetch_council("barnet", tmp_path)
