from dataclasses import dataclass


@dataclass(frozen=True)
class Nation:
    slug: str
    name: str
    note: str


# Static, not model-backed -- no equivalent of England's Local Government
# Transparency Code exists in these nations, so there's no itemised spend
# data to onboard a Council row for. Copy mirrors what the map's grey
# nation overlay used to show inline; now it's the content of the nation's
# own screen (see council_views.nation_dashboard) instead of a map popup.
NATIONS = {
    "wales": Nation(
        "wales",
        "Wales",
        "Wales has no equivalent of England's Local Government Transparency "
        "Code 2015 either. Of 22 councils surveyed, only 3 publish a "
        "spend-over-£500 register -- one council's own FOI response "
        "confirmed Welsh authorities aren't required to.",
    ),
    "scotland": Nation(
        "scotland",
        "Scotland",
        "Scotland has no equivalent of England's Local Government "
        "Transparency Code 2015 -- itemised spend disclosure is voluntary. "
        "Of 32 councils surveyed, only 6 publish anything close to "
        "transaction-level data, at inconsistent thresholds and via "
        "inconsistent channels.",
    ),
    "northern-ireland": Nation(
        "northern-ireland",
        "Northern Ireland",
        "Northern Ireland has no equivalent statutory duty to publish "
        "itemised spend. All 11 district councils were surveyed and none "
        "publish a spend-over-£500 register, so it's out of scope entirely.",
    ),
}
