from django.db import models


class Council(models.Model):
    """Reference data for one London borough.

    `gss_code` is the ONS join key (Register of geographic codes) used to
    match council rows against GeoJSON boundaries later. `slug` matches
    `COUNCIL_NAME` in the upstream parquet files (Phase 2).
    """

    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, unique=True)
    gss_code = models.CharField(max_length=9, unique=True, db_index=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class CouncilCoverage(models.Model):
    """Data-quality join point for a council, one-to-one with Council.

    `earliest_transaction_date`/`latest_transaction_date`/`last_loaded_at`
    are denormalized from `SpendTransaction` by the ETL loader (Phase 2) —
    avoids a live MIN/MAX query on every hover-badge read.
    """

    council = models.OneToOneField(Council, on_delete=models.CASCADE, related_name="coverage")
    has_data_quality_issue = models.BooleanField(default=False)
    detail_text = models.TextField(blank=True, default="")
    earliest_transaction_date = models.DateField(null=True, blank=True)
    latest_transaction_date = models.DateField(null=True, blank=True)
    last_loaded_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Coverage: {self.council.name}"
