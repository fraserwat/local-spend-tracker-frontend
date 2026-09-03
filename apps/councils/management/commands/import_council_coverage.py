from django.core.management.base import BaseCommand, CommandError

from apps.councils.models import CouncilCoverage

# Hand-transcribed from the sibling data repo's README.md, "Coverage &
# date-quality caveats" table (local-big-con-nationwide/README.md), which is
# hand-written prose, not machine-readable -- see docs/ARCHITECTURE.md's data
# model section and Open risk #7. Every loaded council must have an explicit
# entry here, even a clean one, so this stays a verified transcription
# rather than a silent model default standing in for "checked, no issue".
#
# has_data_quality_issue, detail_text
COVERAGE_FIXTURE: dict[str, tuple[bool, str]] = {
    "haringey": (False, ""),
    "barnet": (False, ""),
    "newham": (False, ""),
    "redbridge": (
        True,
        "1,121 rows (£24,679,100) predate Redbridge's first published file "
        "(2010-03); a further 4 rows (£9,594) are dated 2027 or later, past "
        "the source's actual mid-2026 coverage. Both are source date-entry "
        "typos (real supplier + amount, implausible year), retained "
        "verbatim rather than clamped.",
    ),
}


class Command(BaseCommand):
    help = (
        "Apply the hand-transcribed data-quality caveat fixture to existing "
        "CouncilCoverage rows. Run `load_council_spend <slug>` first for any "
        "new council -- that's what creates the row this command updates."
    )

    def handle(self, **options):
        updated = []
        for slug, (has_issue, detail_text) in COVERAGE_FIXTURE.items():
            try:
                coverage = CouncilCoverage.objects.get(council__slug=slug)
            except CouncilCoverage.DoesNotExist as exc:
                raise CommandError(
                    f"no CouncilCoverage row for slug={slug!r} -- run "
                    f"`load_council_spend {slug}` first"
                ) from exc
            coverage.has_data_quality_issue = has_issue
            coverage.detail_text = detail_text
            coverage.save(update_fields=["has_data_quality_issue", "detail_text"])
            updated.append(slug)

        joined = ", ".join(updated)
        self.stdout.write(
            self.style.SUCCESS(f"updated coverage for {len(updated)} council(s): {joined}")
        )
