from django import forms

from .selectors import SORT_FIELDS

SORT_CHOICES = [(key, key) for key in SORT_FIELDS]
DIR_CHOICES = [("asc", "asc"), ("desc", "desc")]


class TransactionFilterForm(forms.Form):
    """Validates the plain GET query params the Spend View filters/sorts by.

    Works with no JS, and gives one place to reject e.g. date_from >
    date_to instead of silently mis-filtering.
    """

    date_from = forms.DateField(required=False)
    date_to = forms.DateField(required=False)
    amount_min = forms.DecimalField(required=False, min_value=0)
    amount_max = forms.DecimalField(required=False, min_value=0)
    q = forms.CharField(required=False, max_length=255)
    sort = forms.ChoiceField(choices=SORT_CHOICES, required=False)
    dir = forms.ChoiceField(choices=DIR_CHOICES, required=False)
    # Rendered disabled with "Coming Soon" -- no backend filtering exists
    # for it yet (Phase 4 scope), so it's never read out of cleaned_data.
    category = forms.CharField(required=False, disabled=True)

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
