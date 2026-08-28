from rest_framework import serializers

from .models import Council


class CouncilSerializer(serializers.ModelSerializer):
    class Meta:
        model = Council
        fields = ["id", "name", "slug", "gss_code", "is_active"]
