import pytest
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory

from apps.councils.models import Council
from apps.spend.admin import SpendTransactionAdmin
from apps.spend.models import SpendTransaction


@pytest.fixture
def council():
    return Council.objects.get(slug="haringey")


@pytest.fixture
def admin_instance():
    return SpendTransactionAdmin(SpendTransaction, AdminSite())


@pytest.mark.django_db
def test_get_queryset_without_filter_returns_empty(admin_instance, council):
    """Unfiltered changelist must not scan every council's rows."""
    SpendTransaction.objects.create(
        council=council, date="2026-01-15", beneficiary_name="Acme Ltd", amount_gbp="100.00"
    )
    request = RequestFactory().get("/admin/spend/spendtransaction/")

    qs = admin_instance.get_queryset(request)

    assert qs.count() == 0


@pytest.mark.django_db
def test_get_queryset_with_filter_param_present_unlocks_unfiltered_queryset(
    admin_instance, council
):
    """`get_queryset` only gates on whether `council__id__exact` is *present* --
    it does not itself narrow rows to that council. The actual per-council
    narrowing happens downstream in the admin changelist's own `list_filter`
    handling. Both councils' rows coming back here (not just `council`'s) is
    the correct, intended behavior for this method, not a bug -- this test
    guards against the gate silently becoming permanent (e.g. always
    returning `.none()` regardless of the param), and against a future
    "fix" that makes this method look like it filters when it doesn't."""
    txn = SpendTransaction.objects.create(
        council=council, date="2026-01-15", beneficiary_name="Acme Ltd", amount_gbp="100.00"
    )
    other = Council.objects.get(slug="camden")
    other_txn = SpendTransaction.objects.create(
        council=other, date="2026-01-16", beneficiary_name="Other Ltd", amount_gbp="50.00"
    )
    request = RequestFactory().get(
        "/admin/spend/spendtransaction/", {"council__id__exact": str(council.id)}
    )

    qs = admin_instance.get_queryset(request)

    assert set(qs) == {txn, other_txn}


@pytest.mark.django_db
@pytest.mark.parametrize("value", ["not-a-number", ""])
def test_get_queryset_gate_checks_key_presence_not_value_validity(admin_instance, council, value):
    """Documents current behavior explicitly: the gate only checks whether the
    key exists in request.GET, not whether its value is a real council id.
    A garbage or empty value still unlocks the full (unfiltered-by-this-
    method) queryset -- same as a valid one -- because value validation is
    Django admin's job downstream, not this method's. If that contract ever
    changes, this test should change with it rather than silently pass."""
    SpendTransaction.objects.create(
        council=council, date="2026-01-15", beneficiary_name="Acme Ltd", amount_gbp="100.00"
    )
    request = RequestFactory().get("/admin/spend/spendtransaction/", {"council__id__exact": value})

    qs = admin_instance.get_queryset(request)

    assert qs.count() == 1


def test_show_full_result_count_is_disabled(admin_instance):
    """A full-table COUNT(*) on every changelist page load doesn't scale to ~300 councils."""
    assert admin_instance.show_full_result_count is False


def test_list_per_page_is_set(admin_instance):
    assert admin_instance.list_per_page == 100
