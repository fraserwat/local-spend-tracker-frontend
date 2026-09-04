import hashlib
import io
import json
from datetime import datetime

import boto3
import polars as pl
import pytest
from moto import mock_aws

from apps.spend.services import r2

BUCKET = "test-bucket"


@pytest.fixture
def r2_settings(settings):
    settings.R2_ACCOUNT_ID = "test-account"
    settings.R2_ACCESS_KEY_ID = "test-key"
    settings.R2_SECRET_ACCESS_KEY = "test-secret"
    settings.R2_BUCKET = BUCKET


@pytest.fixture
def s3_client(r2_settings, monkeypatch):
    # moto intercepts requests to real AWS endpoints; r2.py's _client()
    # builds a custom R2 endpoint_url that moto won't recognize, so the
    # call would otherwise escape the mock and hit real DNS/SSL. Patch
    # _client() to hand back this same moto-backed client instead --
    # production _client() (real endpoint_url, region_name="auto") is
    # untouched.
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET)
        monkeypatch.setattr(r2, "_client", lambda: client)
        yield client


def _curated_parquet_bytes(slug: str) -> bytes:
    df = pl.DataFrame(
        [
            {
                "COUNCIL_NAME": slug,
                "DATE": datetime(2026, 1, 15),
                "BENEFICIARY_NAME": "Acme Ltd",
                "AMOUNT_GBP": 100.0,
                "DIRECTORATE": None,
                "CATEGORY": None,
                "SUB_CATEGORY": None,
                "DESCRIPTION": None,
            }
        ]
    )
    buf = io.BytesIO()
    df.write_parquet(buf)
    return buf.getvalue()


def _seed_council(client, slug: str, *, corrupt_parquet: bool = False) -> None:
    parquet_bytes = _curated_parquet_bytes(slug)
    sha256 = hashlib.sha256(parquet_bytes).hexdigest()
    manifest = {
        "schema_version": 1,
        "council": slug,
        "source_run": "nightly",
        "updated_at": "2026-09-04T13:36:06Z",
        "curated": {
            "key": f"curated/{slug}.parquet",
            "row_count": 1,
            "size_bytes": len(parquet_bytes),
            "etag": "irrelevant",
            "sha256": sha256,
            "amount_total_gbp": 100.0,
            "date_min": "2026-01-15 00:00:00",
            "date_max": "2026-01-15 00:00:00",
        },
    }
    client.put_object(
        Bucket=BUCKET, Key=f"manifest/{slug}.json", Body=json.dumps(manifest).encode()
    )
    if corrupt_parquet:
        parquet_bytes = parquet_bytes + b"\x00corrupt"
    client.put_object(Bucket=BUCKET, Key=f"curated/{slug}.parquet", Body=parquet_bytes)


def test_list_councils_returns_sorted_slugs(s3_client):
    _seed_council(s3_client, "barnet")
    _seed_council(s3_client, "adur")
    # A stray curated/raw object with no matching manifest must not leak in.
    s3_client.put_object(Bucket=BUCKET, Key="curated/orphan.parquet", Body=b"x")

    assert r2.list_councils() == ["adur", "barnet"]


def test_list_councils_raises_r2error_when_config_incomplete(r2_settings, settings):
    settings.R2_BUCKET = ""
    with pytest.raises(r2.R2Error, match="incomplete"):
        r2.list_councils()


def test_fetch_council_downloads_and_verifies_matching_files(s3_client, tmp_path):
    _seed_council(s3_client, "barnet")

    fetched = r2.fetch_council("barnet", tmp_path)

    assert fetched.manifest["council"] == "barnet"
    assert fetched.parquet_path.exists()
    assert fetched.parquet_path.read_bytes() == _curated_parquet_bytes("barnet")


def test_fetch_council_raises_on_sha256_mismatch(s3_client, tmp_path):
    _seed_council(s3_client, "barnet", corrupt_parquet=True)

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
