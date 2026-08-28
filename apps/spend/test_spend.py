import pytest

from apps.councils.models import Council
from apps.spend.models import DataLoadRun, SpendTransaction


@pytest.fixture
def council():
    return Council.objects.get(slug="haringey")


@pytest.mark.django_db
def test_spend_transaction_create(council):
    txn = SpendTransaction.objects.create(
        council=council,
        date="2026-01-15",
        beneficiary_name="Acme Consulting Ltd",
        amount_gbp="12345.67",
    )
    assert txn.directorate == ""
    assert txn.category == ""
    assert council.transactions.count() == 1


@pytest.mark.django_db
def test_data_load_run_defaults_to_running(council):
    run = DataLoadRun.objects.create(council=council, source_file_path="/data/haringey.parquet")
    assert run.status == DataLoadRun.Status.RUNNING
    assert run.finished_at is None
