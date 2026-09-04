import tempfile
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.councils.models import Council
from apps.spend.models import DataLoadRun
from apps.spend.services.etl import load_council_spend
from apps.spend.services.r2 import (
    R2Error,
    fetch_council,
    fetch_manifest,
    list_councils,
    normalize_slug,
)


class Command(BaseCommand):
    help = (
        "Diff every loaded council's R2 manifest against its last successful load's "
        "sha256 and reload only what actually changed. Never aborts the batch on one "
        "council's failure -- continues to the rest and exits non-zero if any failed."
    )

    def add_arguments(self, parser):
        parser.add_argument("--slug", help="Only process this council slug.")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without loading or writing anything.",
        )

    def handle(self, slug, dry_run, **options):
        if slug:
            try:
                councils = [Council.objects.get(slug=slug)]
            except Council.DoesNotExist as exc:
                raise CommandError(f"no Council with slug={slug!r}") from exc
        else:
            councils = list(Council.objects.order_by("slug"))

        available = set(list_councils())

        all_ok = True
        for council in councils:
            ok, message = self._process_one(council, available, dry_run)
            all_ok &= ok
            style = self.style.SUCCESS if ok else self.style.ERROR
            self.stdout.write(style(f"{council.slug:25} {message}"))

        if not all_ok:
            raise CommandError("one or more councils failed -- see output above")

    def _process_one(
        self, council: Council, available: set[str], dry_run: bool
    ) -> tuple[bool, str]:
        r2_slug = normalize_slug(council.slug)
        if r2_slug not in available:
            return True, "SKIPPED (not yet in R2)"

        try:
            manifest = fetch_manifest(r2_slug)
            manifest_sha256 = manifest["curated"]["sha256"]
        except R2Error as exc:
            self._record_fetch_failure(council, r2_slug, exc)
            return False, f"FAILED (fetch: {exc})"
        except (KeyError, TypeError):
            self._record_fetch_failure(council, r2_slug, "manifest missing curated.sha256")
            return False, "FAILED (fetch: manifest missing curated.sha256)"

        last_success = council.load_runs.filter(status=DataLoadRun.Status.SUCCESS).first()
        if last_success is not None and last_success.source_sha256 == manifest_sha256:
            return True, "UNCHANGED"

        if dry_run:
            return True, "WOULD RELOAD"

        with tempfile.TemporaryDirectory() as tmp_dir:
            try:
                fetched = fetch_council(r2_slug, Path(tmp_dir))
            except R2Error as exc:
                self._record_fetch_failure(council, r2_slug, exc)
                return False, f"FAILED (fetch: {exc})"

            try:
                run = load_council_spend(council, fetched.parquet_path)
            except Exception as exc:
                return False, f"FAILED (load: {exc})"

            run.source_sha256 = fetched.manifest["curated"]["sha256"]
            run.save(update_fields=["source_sha256"])
            return True, f"RELOADED ({run.row_count} rows)"

    def _record_fetch_failure(self, council: Council, r2_slug: str, error: object) -> None:
        # Closes the gap where an R2-fetch failure (bad manifest, sha256
        # mismatch) happened before load_council_spend ever ran, so no
        # DataLoadRun captured it -- visible only in job logs otherwise.
        DataLoadRun.objects.create(
            council=council,
            source_file_path=f"r2://{r2_slug}",
            status=DataLoadRun.Status.FAILED,
            error_message=str(error),
            finished_at=timezone.now(),
        )
