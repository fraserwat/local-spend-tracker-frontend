from datetime import date
from decimal import Decimal

import polars as pl
import pytest

from apps.councils.models import Council
from apps.spend.models import SpendTransaction
from apps.spend.selectors import get_council_transactions


@pytest.fixture
def council():
    return Council.objects.get(slug="haringey")


@pytest.fixture
def other_council():
    return Council.objects.get(slug="camden")


@pytest.fixture
def rows(council, other_council):
    """A small, hand-verifiable dataset -- also used for the Polars cross-check below."""
    data = [
        {
            "date": date(2026, 1, 5),
            "beneficiary_name": "Acme Consulting Ltd",
            "amount_gbp": "100.00",
        },
        {"date": date(2026, 1, 20), "beneficiary_name": "Beta Supplies", "amount_gbp": "250.50"},
        {"date": date(2026, 2, 10), "beneficiary_name": "Acme Facilities", "amount_gbp": "75.25"},
        {"date": date(2026, 3, 1), "beneficiary_name": "Gamma Consulting", "amount_gbp": "1000.00"},
    ]
    created = [SpendTransaction.objects.create(council=council, **row) for row in data]
    # A different council's row with an overlapping amount/date --
    # filters must not leak across councils.
    SpendTransaction.objects.create(
        council=other_council,
        date=date(2026, 1, 5),
        beneficiary_name="Acme Consulting Ltd",
        amount_gbp="100.00",
    )
    return created


@pytest.mark.django_db
def test_filters_by_date_range(council, rows):
    result = get_council_transactions(
        council, date_from=date(2026, 1, 10), date_to=date(2026, 2, 28)
    )
    assert {t.beneficiary_name for t in result} == {"Beta Supplies", "Acme Facilities"}


@pytest.mark.django_db
def test_filters_by_amount_range(council, rows):
    result = get_council_transactions(
        council, amount_min=Decimal("100.00"), amount_max=Decimal("300.00")
    )
    assert {t.beneficiary_name for t in result} == {"Acme Consulting Ltd", "Beta Supplies"}


@pytest.mark.django_db
def test_filters_by_beneficiary_search_case_insensitive(council, rows):
    result = get_council_transactions(council, q="ACME")
    assert {t.beneficiary_name for t in result} == {"Acme Consulting Ltd", "Acme Facilities"}


@pytest.mark.django_db
def test_beneficiary_search_treats_query_as_literal_substring(council, rows):
    """Regex metacharacters in the search term (e.g. from a beneficiary name
    containing "." or "&") must not be interpreted as regex syntax -- the
    iregex lookup only exists to reach the trigram index, not to expose a
    user-facing regex search."""
    SpendTransaction.objects.create(
        council=council,
        date=date(2026, 4, 1),
        beneficiary_name="A.C.M.E (Holdings)",
        amount_gbp="50.00",
    )
    result = get_council_transactions(council, q="A.C.M.E (Holdings)")
    assert {t.beneficiary_name for t in result} == {"A.C.M.E (Holdings)"}


@pytest.mark.django_db
def test_filters_never_leak_across_councils(council, rows):
    result = get_council_transactions(council)
    assert result.count() == 4
    assert all(t.council_id == council.id for t in result)


@pytest.mark.django_db
def test_sort_by_amount_ascending(council, rows):
    result = list(get_council_transactions(council, sort="amount_gbp", descending=False))
    amounts = [t.amount_gbp for t in result]
    assert amounts == sorted(amounts)


@pytest.mark.django_db
def test_sort_by_amount_descending(council, rows):
    result = list(get_council_transactions(council, sort="amount_gbp", descending=True))
    amounts = [t.amount_gbp for t in result]
    assert amounts == sorted(amounts, reverse=True)


@pytest.mark.django_db
def test_unknown_sort_field_falls_back_to_default(council, rows):
    """Reads straight from query params -- must degrade safely, not raise, on
    an unrecognised value (e.g. a stale bookmarked link after a field is
    renamed)."""
    result = list(get_council_transactions(council, sort="not_a_real_field"))
    dates = [t.date for t in result]
    assert dates == sorted(dates, reverse=True)


@pytest.mark.django_db
def test_sort_is_stable_via_id_tiebreaker(council):
    """Two rows sharing the sorted-on value (date) must still come back in a
    deterministic order, not vary run to run -- required for keyset
    pagination to never skip or repeat a row across pages."""
    a = SpendTransaction.objects.create(
        council=council, date=date(2026, 1, 1), beneficiary_name="Same Day A", amount_gbp="10.00"
    )
    b = SpendTransaction.objects.create(
        council=council, date=date(2026, 1, 1), beneficiary_name="Same Day B", amount_gbp="20.00"
    )
    result = list(get_council_transactions(council, sort="date", descending=True))
    assert result == sorted([a, b], key=lambda t: -t.id)


@pytest.mark.django_db
def test_filtered_total_matches_equivalent_polars_query(council, rows):
    """Cross-check against an independent implementation of the same filter,
    per docs/TODO.md's Phase 4 verify step -- catches a selector bug that a
    Django-only test (which could share the same wrong assumption) would miss."""
    frame = pl.DataFrame(
        [
            {
                "beneficiary_name": t.beneficiary_name,
                "amount_gbp": float(t.amount_gbp),
                "date": t.date,
            }
            for t in SpendTransaction.objects.filter(council=council)
        ]
    )
    expected = frame.filter((pl.col("date") >= date(2026, 1, 10)) & (pl.col("amount_gbp") <= 300.0))
    expected_total = round(expected["amount_gbp"].sum(), 2)
    expected_count = expected.height

    result = get_council_transactions(
        council, date_from=date(2026, 1, 10), amount_max=Decimal("300.00")
    )
    actual_count = result.count()
    actual_total = sum(t.amount_gbp for t in result)

    assert actual_count == expected_count
    assert actual_total == Decimal(str(expected_total))
