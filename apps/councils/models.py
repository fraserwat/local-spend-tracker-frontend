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

    Deliberately minimal for Phase 1 — just enough to hang a future hover
    badge (Phase 6) off of. Denormalized date fields, pre-coverage row
    counts etc. are added later once the ETL loader (Phase 2) exists to
    populate them.
    """

    council = models.OneToOneField(Council, on_delete=models.CASCADE, related_name="coverage")
    has_data_quality_issue = models.BooleanField(default=False)
    detail_text = models.TextField(blank=True, default="")

    def __str__(self):
        return f"Coverage: {self.council.name}"
