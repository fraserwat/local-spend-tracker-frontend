from django.db import models

from apps.councils.models import Council

# GBP amounts always carry pence-level precision. Shared with the rounding
# step in apps/spend/services/etl.py so both stay in sync.
AMOUNT_DECIMAL_PLACES = 2


class SpendTransaction(models.Model):
    """One row of council spend, loaded verbatim from the upstream parquet.

    `beneficiary_name` is unresolved (no entity dedup exists upstream) —
    deliberately no FK to any consultancy table so the parked "by-consultancy
    spend" feature can be added later as a separate lookup table joined by
    name at query time. `directorate`/`category`/`sub_category`/`description`
    are sparse across councils, hence blank-default rather than nullable.

    No natural key / unique_together — there is no dedup key upstream, so
    duplicate-prevention lives in the ETL load strategy (full-replace per
    council), not the schema.
    """

    council = models.ForeignKey(Council, on_delete=models.CASCADE, related_name="transactions")
    date = models.DateField()
    beneficiary_name = models.CharField(max_length=255)
    amount_gbp = models.DecimalField(max_digits=14, decimal_places=AMOUNT_DECIMAL_PLACES)
    directorate = models.CharField(max_length=255, blank=True, default="")
    category = models.CharField(max_length=255, blank=True, default="")
    sub_category = models.CharField(max_length=255, blank=True, default="")
    description = models.TextField(blank=True, default="")

    class Meta:
        indexes = [
            models.Index(fields=["council", "date"]),
            models.Index(fields=["council", "amount_gbp"]),
        ]

    def __str__(self):
        return f"{self.council.name}: {self.beneficiary_name} ({self.amount_gbp})"


class DataLoadRun(models.Model):
    """Audit log for one ETL loader invocation.

    Written as status="running" and committed *before* the delete+insert
    transaction starts, then updated to "success"/"failed" in its own
    transaction afterward — so a crash mid-load leaves a visible failure
    record rather than erasing it along with the rolled-back payload.
    """

    class Status(models.TextChoices):
        RUNNING = "running", "Running"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"

    council = models.ForeignKey(Council, on_delete=models.CASCADE, related_name="load_runs")
    source_file_path = models.CharField(max_length=500)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    row_count = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.RUNNING)
    error_message = models.TextField(blank=True, default="")
    # The R2 manifest's curated.sha256 at load time -- blank for
    # --source-dir loads (no manifest to read). Lets reload_from_r2 diff
    # "has this council's data actually changed" without re-downloading
    # parquet just to check.
    source_sha256 = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.council.name} load @ {self.started_at:%Y-%m-%d %H:%M} ({self.status})"
