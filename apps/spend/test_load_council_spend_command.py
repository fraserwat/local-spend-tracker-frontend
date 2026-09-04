from datetime import datetime
from io import StringIO

import polars as pl
import pytest
from django.core.management import call_command

from apps.councils.models import Council
from apps.spend.models import SpendTransaction


@pytest.mark.django_db
def test_command_maps_hyphenated_slug_to_underscored_filename(tmp_path):
    # migration 0002 already seeds all 32 London boroughs, Tower Hamlets
    # included -- fetch it rather than creating a duplicate slug.
    council = Council.objects.get(slug="tower-hamlets")
    # Sibling repo's curated filenames use underscores, not hyphens.
    source = tmp_path / "tower_hamlets.parquet"
    pl.DataFrame(
        [
            {
                "COUNCIL_NAME": "tower_hamlets",
                "DATE": datetime(2026, 1, 15),
                "BENEFICIARY_NAME": "Acme Consulting Ltd",
                "AMOUNT_GBP": 100.0,
                "DIRECTORATE": "",
                "CATEGORY": "",
                "SUB_CATEGORY": "",
                "DESCRIPTION": "",
            }
        ]
    ).write_parquet(source)

    call_command(
        "load_council_spend", "tower-hamlets", "--source-dir", str(tmp_path), stdout=StringIO()
    )

    assert SpendTransaction.objects.filter(council=council).count() == 1
