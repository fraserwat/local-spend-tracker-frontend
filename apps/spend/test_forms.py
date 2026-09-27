from datetime import date

from apps.spend.forms import TransactionFilterForm


def _form(**overrides):
    data = {"date_from_0": "", "date_from_1": "", "date_from_2": "", "sort": "", "dir": ""}
    data.update(overrides)
    return TransactionFilterForm(data)


def test_day_month_year_field_compresses_a_complete_date():
    form = _form(date_from_0="14", date_from_1="3", date_from_2="2026")
    assert form.is_valid(), form.errors
    assert form.cleaned_data["date_from"] == date(2026, 3, 14)


def test_day_month_year_field_all_blank_is_none_not_an_error():
    form = _form()
    assert form.is_valid(), form.errors
    assert form.cleaned_data["date_from"] is None


def test_day_month_year_field_rejects_a_partial_date():
    form = _form(date_from_0="14", date_from_1="3")
    assert not form.is_valid()
    assert "date_from" in form.errors


def test_day_month_year_field_rejects_an_impossible_date():
    form = _form(date_from_0="31", date_from_1="2", date_from_2="2026")
    assert not form.is_valid()
    assert "date_from" in form.errors
