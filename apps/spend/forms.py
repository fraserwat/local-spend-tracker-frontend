from datetime import date as date_cls

from django import forms

from .selectors import SORT_FIELDS

SORT_CHOICES = [(key, key) for key in SORT_FIELDS]
DIR_CHOICES = [("asc", "asc"), ("desc", "desc")]


class DayMonthYearWidget(forms.MultiWidget):
    """Three plain number inputs (day, month, year) instead of one text field
    with an implicit format -- GOV.UK's date-input pattern: typing a date you
    already know beats navigating a calendar popup, and three small fields
    make the expected shape self-evident without a placeholder to misread.
    https://design-system.service.gov.uk/components/date-input/
    """

    template_name = "spend/widgets/day_month_year.html"

    def __init__(self, attrs=None):
        widgets = [
            forms.NumberInput(
                attrs={"placeholder": "DD", "class": "field dmy-day", "min": 1, "max": 31}
            ),
            forms.NumberInput(
                attrs={"placeholder": "MM", "class": "field dmy-month", "min": 1, "max": 12}
            ),
            forms.NumberInput(
                attrs={"placeholder": "YYYY", "class": "field dmy-year", "min": 1900, "max": 2100}
            ),
        ]
        super().__init__(widgets, attrs)

    def decompress(self, value):
        if isinstance(value, date_cls):
            return [value.day, value.month, value.year]
        return [None, None, None]


class DayMonthYearField(forms.MultiValueField):
    def __init__(self, **kwargs):
        fields = (
            forms.IntegerField(min_value=1, max_value=31, required=False),
            forms.IntegerField(min_value=1, max_value=12, required=False),
            forms.IntegerField(min_value=1900, max_value=2100, required=False),
        )
        kwargs.setdefault("require_all_fields", False)
        super().__init__(fields, widget=DayMonthYearWidget(), **kwargs)

    def compress(self, data_list):
        if not data_list:
            return None
        day, month, year = data_list
        if day is None and month is None and year is None:
            return None
        if day is None or month is None or year is None:
            raise forms.ValidationError("Enter a complete date (day, month and year).")
        try:
            return date_cls(year, month, day)
        except ValueError as exc:
            raise forms.ValidationError("Enter a real date.") from exc


class TransactionFilterForm(forms.Form):
    """Validates the plain GET query params the Spend View filters/sorts by.

    Works with no JS, and gives one place to reject e.g. date_from >
    date_to instead of silently mis-filtering.
    """

    date_from = DayMonthYearField(required=False)
    date_to = DayMonthYearField(required=False)
    amount_min = forms.DecimalField(
        required=False,
        min_value=0,
        widget=forms.NumberInput(attrs={"class": "field", "placeholder": "Min"}),
    )
    amount_max = forms.DecimalField(
        required=False,
        min_value=0,
        widget=forms.NumberInput(attrs={"class": "field", "placeholder": "Max"}),
    )
    q = forms.CharField(
        required=False,
        max_length=255,
        widget=forms.TextInput(
            attrs={"class": "field", "placeholder": "Search by name", "autocomplete": "off"}
        ),
    )
    sort = forms.ChoiceField(choices=SORT_CHOICES, required=False)
    dir = forms.ChoiceField(choices=DIR_CHOICES, required=False)
    # Keyword-proxy filter, not real entity resolution -- see
    # category_buckets.CONSULTANCY_KEYWORDS and selectors.get_council_transactions.
    consultancy = forms.BooleanField(
        required=False, widget=forms.CheckboxInput(attrs={"class": "consultancy-checkbox"})
    )

    def clean(self):
        cleaned = super().clean()
        date_from, date_to = cleaned.get("date_from"), cleaned.get("date_to")
        if date_from and date_to and date_from > date_to:
            raise forms.ValidationError("date_from must not be after date_to.")

        amount_min, amount_max = cleaned.get("amount_min"), cleaned.get("amount_max")
        if amount_min is not None and amount_max is not None and amount_min > amount_max:
            raise forms.ValidationError("amount_min must not be greater than amount_max.")

        return cleaned

    @property
    def sort_field(self) -> str:
        """Renamed from the `sort` form field to avoid shadowing it as a class attribute."""
        return self.cleaned_data.get("sort") or "date"

    @property
    def descending(self) -> bool:
        return self.cleaned_data.get("dir", "desc") != "asc"
