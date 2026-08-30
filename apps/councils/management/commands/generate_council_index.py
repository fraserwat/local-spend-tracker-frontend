import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.councils.models import Council, Region

DEFAULT_OUTPUT_PATH = (
    Path(settings.BASE_DIR)
    / "apps"
    / "councils"
    / "static"
    / "councils"
    / "data"
    / "council-index.json"
)


class Command(BaseCommand):
    help = (
        "Generate the static council-index.json used by the picker page's search "
        "widget (apps/councils/templates/councils/picker.html). Server-rendered "
        "region groups on that same page read the DB directly instead -- this "
        "file only backs the client-side autocomplete."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            default=str(DEFAULT_OUTPUT_PATH),
            help="Destination path for the generated JSON (defaults to the committed static file).",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Write even if the council count would shrink versus the existing output file "
            "(guards against accidentally overwriting the committed index with a wrong-DB or "
            "near-empty run).",
        )

    def handle(self, output, force, **options):
        councils = Council.objects.filter(is_active=True).order_by("name")
        rows = []
        for council in councils:
            try:
                region_display = Region(council.region).label
            except ValueError as exc:
                raise CommandError(
                    f"council {council.slug!r} has region={council.region!r}, "
                    f"not one of Region's valid choices"
                ) from exc
            rows.append(
                {
                    "name": council.name,
                    "slug": council.slug,
                    "region": council.region,
                    "region_display": region_display,
                }
            )

        output_path = Path(output)
        if output_path.exists() and not force:
            try:
                existing_count = len(json.loads(output_path.read_text()))
            except (json.JSONDecodeError, OSError):
                existing_count = None
            if existing_count is not None and len(rows) < existing_count:
                raise CommandError(
                    f"refusing to shrink {output_path} from {existing_count} to {len(rows)} "
                    "councils -- pass --force if this is expected (e.g. councils deactivated)"
                )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(rows, indent=2) + "\n")

        self.stdout.write(self.style.SUCCESS(f"wrote {len(rows)} councils to {output_path}"))
