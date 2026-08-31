from django.contrib import admin

from .models import DataLoadRun, SpendTransaction


@admin.register(SpendTransaction)
class SpendTransactionAdmin(admin.ModelAdmin):
    list_display = ("council", "date", "beneficiary_name", "amount_gbp")
    list_filter = ("council",)
    list_select_related = ("council",)
    search_fields = ("beneficiary_name",)
    ordering = ("-date",)
    list_per_page = 100
    show_full_result_count = False

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if "council__id__exact" not in request.GET:
            # Cross-council browsing needs its own aggregate view once that
            # feature exists — until then, an unfiltered changelist would
            # run a full-table COUNT(*) and scan across every council.
            return qs.none()
        return qs


@admin.register(DataLoadRun)
class DataLoadRunAdmin(admin.ModelAdmin):
    list_display = ("council", "started_at", "status", "row_count")
    list_filter = ("status", "council")
    ordering = ("-started_at",)
