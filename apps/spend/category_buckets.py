"""Maps a council's raw free-text spend category into one of a small set of
semantic buckets, for the category pill's color only. `category` comes from
each council's own finance system with no shared vocabulary across councils
(see SpendTransaction.category), so this is a best-effort keyword scan, not
a lookup table -- anything unmatched falls into OTHER rather than raising.
"""

from dataclasses import dataclass
from functools import cache


@dataclass(frozen=True)
class CategoryBucket:
    slug: str
    label: str


OTHER = CategoryBucket("other", "Admin, overhead & other")

# Checked in order -- first keyword match wins. Order matters where a
# category could plausibly match more than one bucket.
_BUCKETS = (
    (
        CategoryBucket("staff", "Staff & people"),
        ("staff", "employee", "agency", "salar", "payroll", "training", "compensation"),
    ),
    (
        CategoryBucket("contracts", "Contracts & professional"),
        ("consult", "contract", "professional fee", "legal", "advis"),
    ),
    (
        CategoryBucket("capital", "Capital & infrastructure"),
        ("capital", "infrastructure", "property acquisition"),
    ),
    (
        CategoryBucket("premises", "Premises & operations"),
        (
            "premises",
            "repair",
            "maintenance",
            "utilit",
            "vehicle",
            "fuel",
            "cleaning",
            "catering",
            "supplies",
        ),
    ),
    (
        CategoryBucket("grants", "Grants & third-party"),
        ("grant", "subsid", "voluntary", "rent", "lease", "third party", "third-party"),
    ),
)


@cache
def bucket_for(category: str) -> CategoryBucket:
    lowered = category.lower()
    for bucket, keywords in _BUCKETS:
        if any(keyword in lowered for keyword in keywords):
            return bucket
    return OTHER
