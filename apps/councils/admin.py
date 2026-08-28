from django.contrib import admin

from .models import Council, CouncilCoverage


@admin.register(Council)
class CouncilAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "gss_code", "is_active")
    search_fields = ("name", "slug", "gss_code")
    ordering = ("name",)


@admin.register(CouncilCoverage)
class CouncilCoverageAdmin(admin.ModelAdmin):
    list_display = ("council", "has_data_quality_issue")
    list_filter = ("has_data_quality_issue",)
    search_fields = ("council__name",)
