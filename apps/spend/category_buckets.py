"""Maps a council's raw free-text spend category into one of a small set of
semantic buckets, for the category pill's color only. `category` comes from
each council's own finance system with no shared vocabulary across councils
(see SpendTransaction.category), so this is a best-effort keyword scan, not
a lookup table -- anything unmatched falls into OTHER rather than raising.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class CategoryBucket:
    slug: str
    label: str


OTHER = CategoryBucket("other", "Admin, overhead & other")

# PLACEHOLDER -- also used by apps/spend/views.py as a stand-in for real
# entity-resolved consultancy spend (see TODO.md Phase 3). Free-text
# category keyword match, not a lookup table; "consult"/"contract"/
# "advis" over-match generic contracted services that aren't consultancy,
# and payments never *labelled* with these words in a council's own
# category field are silently excluded. Named here, not inline in
# views.py, so the two call sites can't drift apart.
CONTRACTS_KEYWORDS = ("consult", "contract", "professional fee", "legal", "advis")

# Checked in order -- first keyword match wins. Order matters where a
# category could plausibly match more than one bucket.
_BUCKETS = (
    (
        CategoryBucket("staff", "Staff & people"),
        ("staff", "employee", "agency", "salar", "payroll", "training", "compensation"),
    ),
    (
        CategoryBucket("contracts", "Contracts & professional"),
        CONTRACTS_KEYWORDS,
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


def bucket_for(category: str) -> CategoryBucket:
    lowered = category.lower()
    for bucket, keywords in _BUCKETS:
        if any(keyword in lowered for keyword in keywords):
            return bucket
    return OTHER
