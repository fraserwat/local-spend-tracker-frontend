import hashlib
import io
import json
from datetime import date, datetime, timedelta

import boto3
import polars as pl
import pytest
from moto import mock_aws

from apps.councils.models import Council
from apps.spend.models import SpendTransaction
from apps.spend.services import r2

BUCKET = "test-bucket"


@pytest.fixture
def council():
    return Council.objects.get(slug="haringey")


@pytest.fixture
def rows(council):
    base = date(2026, 1, 1)
    return [
        SpendTransaction.objects.create(
            council=council,
            date=base + timedelta(days=i),
            beneficiary_name=f"Vendor {i:02d}",
            amount_gbp=f"{(i + 1) * 10}.00",
        )
        for i in range(5)
    ]


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


def curated_parquet_bytes(slug: str, *, row_count: int = 1) -> bytes:
    df = pl.DataFrame(
        [
            {
                "COUNCIL_NAME": slug,
                "DATE": datetime(2026, 1, 15),
                "BENEFICIARY_NAME": "Acme Ltd",
                "AMOUNT_GBP": 100.0,
                "DIRECTORATE": "",
                "CATEGORY": "",
                "SUB_CATEGORY": "",
                "DESCRIPTION": "",
            }
        ]
        * row_count
    )
    buf = io.BytesIO()
    df.write_parquet(buf)
    return buf.getvalue()


def seed_council(client, slug: str, *, corrupt_parquet: bool = False) -> None:
    parquet_bytes = curated_parquet_bytes(slug)
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
