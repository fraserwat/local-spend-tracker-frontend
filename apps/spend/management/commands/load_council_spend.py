from pathlib import Path

import polars as pl
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.councils.models import Council
from apps.spend.services.etl import EXPECTED_COLUMNS, load_council_spend


class Command(BaseCommand):
    help = "Load one council's curated spend parquet into Postgres (full-replace)."

    def add_arguments(self, parser):
        parser.add_argument("slug", help="Council slug, e.g. haringey")
        parser.add_argument(
            "--source-dir",
            help="Directory containing <slug>.parquet. Defaults to settings.SPEND_SOURCE_DIR.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate the source file without writing to the database.",
        )

    def handle(self, slug, source_dir, dry_run, **options):
        try:
            council = Council.objects.get(slug=slug)
        except Council.DoesNotExist as exc:
            raise CommandError(f"no Council with slug={slug!r}") from exc

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
