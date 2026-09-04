import tempfile
from pathlib import Path

import polars as pl
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.councils.models import Council
from apps.spend.services.etl import EXPECTED_COLUMNS, load_council_spend
from apps.spend.services.r2 import R2Error, fetch_council


class Command(BaseCommand):
    help = (
        "Load one council's curated spend parquet into Postgres (full-replace), "
        "from a local directory or R2."
    )

    def add_arguments(self, parser):
        parser.add_argument("slug", help="Council slug, e.g. haringey")
        source_group = parser.add_mutually_exclusive_group()
        source_group.add_argument(
            "--source-dir",
            help="Directory containing <slug>.parquet. Defaults to settings.SPEND_SOURCE_DIR.",
        )
        source_group.add_argument(
            "--from-r2",
            action="store_true",
            help="Fetch curated parquet + manifest from R2 instead of a local directory.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate the source file without writing to the database.",
        )

    def handle(self, slug, source_dir, from_r2, dry_run, **options):
        try:
            council = Council.objects.get(slug=slug)
        except Council.DoesNotExist as exc:
            raise CommandError(f"no Council with slug={slug!r}") from exc

        if from_r2:
            self._handle_from_r2(council, slug, dry_run)
            return

        source_dir = source_dir or getattr(settings, "SPEND_SOURCE_DIR", None)
        if not source_dir:
            raise CommandError("--source-dir not given and settings.SPEND_SOURCE_DIR not set")

        # Sibling repo's curated filenames use underscores (its own
        # naming convention); Django's slugify produces hyphens. Only
        # single-word slugs have been loaded so far, so this mismatch
        # was latent until multi-word boroughs (e.g. tower-hamlets).
        source_path = Path(source_dir) / f"{slug.replace('-', '_')}.parquet"
        if not source_path.exists():
            raise CommandError(f"source file not found: {source_path}")

        if dry_run:
            df = pl.read_parquet(source_path)
            if set(df.columns) != EXPECTED_COLUMNS:
                raise CommandError(f"column mismatch: found {set(df.columns)}")
            self.stdout.write(f"dry-run OK: {source_path} has {len(df)} rows, columns match")
            return

        run = load_council_spend(council, source_path)
        self.stdout.write(self.style.SUCCESS(f"loaded {run.row_count} rows for {council.name}"))

    def _handle_from_r2(self, council, slug, dry_run):
        # Same hyphen->underscore normalization as --source-dir: R2 object
        # keys use the sibling repo's own filename stems (underscored).
        r2_slug = slug.replace("-", "_")
        with tempfile.TemporaryDirectory() as tmp_dir:
            try:
                fetched = fetch_council(r2_slug, Path(tmp_dir))
            except R2Error as exc:
                raise CommandError(str(exc)) from exc

            if dry_run:
                df = pl.read_parquet(fetched.parquet_path)
                if set(df.columns) != EXPECTED_COLUMNS:
                    raise CommandError(f"column mismatch: found {set(df.columns)}")
                self.stdout.write(
                    f"dry-run OK: r2://{r2_slug} manifest row_count="
                    f"{fetched.manifest['curated']['row_count']}, downloaded {len(df)} rows, "
                    "columns match, sha256 verified"
                )
                return

            # Load while the temp dir (and its parquet file) is still alive --
            # load_council_spend reads it directly, no separate copy.
            run = load_council_spend(council, fetched.parquet_path)
            self.stdout.write(self.style.SUCCESS(f"loaded {run.row_count} rows for {council.name}"))
