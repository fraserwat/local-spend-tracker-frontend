"""Keyword list for the Consultancy filter's category match. `category`
comes from each council's own finance system with no shared vocabulary
across councils (see SpendTransaction.category), so this is a best-effort
keyword scan, not a lookup table -- it both over- and under-counts real
consultancy spend. Stands in for real entity-resolved consultancy spend
until the Entity Resolution Layer (TODO.md Phase 3) ships.
"""

CONSULTANCY_KEYWORDS = ("consult", "contract", "professional fee", "legal", "advis")
