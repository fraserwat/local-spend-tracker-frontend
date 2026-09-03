from rest_framework import serializers

from .models import Council, CouncilCoverage


class CouncilSerializer(serializers.ModelSerializer):
    class Meta:
        model = Council
        fields = ["id", "name", "slug", "gss_code", "is_active"]


class CoverageSerializer(serializers.ModelSerializer):
    class Meta:
        model = CouncilCoverage
        fields = [
            "has_data_quality_issue",
            "detail_text",
            "earliest_transaction_date",
            "latest_transaction_date",
            "last_loaded_at",
        ]
