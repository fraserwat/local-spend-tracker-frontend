from django.contrib import admin

from .models import DataLoadRun, SpendTransaction


@admin.register(SpendTransaction)
class SpendTransactionAdmin(admin.ModelAdmin):
    list_display = ("council", "date", "beneficiary_name", "amount_gbp")
    list_filter = ("council",)
    search_fields = ("beneficiary_name", "description")
    ordering = ("-date",)


@admin.register(DataLoadRun)
class DataLoadRunAdmin(admin.ModelAdmin):
    list_display = ("council", "started_at", "status", "row_count")
    list_filter = ("status", "council")
    ordering = ("-started_at",)
