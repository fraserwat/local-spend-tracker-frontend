from rest_framework import serializers

from .models import SpendTransaction


class SpendTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = SpendTransaction
        fields = [
            "id",
            "date",
            "beneficiary_name",
            "amount_gbp",
            "directorate",
            "category",
            "sub_category",
            "description",
        ]
