from django.core.management.base import BaseCommand, CommandError

from apps.councils.models import CouncilCoverage

# Sourced from local-big-con-nationwide's per-council config comments
# (configs/councils/<slug>.yaml, the header block above `council_name:`) --
# confirmed as the source of truth over that repo's README summary table,
# which only ever covered the original 18-council London pilot batch and
# only one issue category (pre-coverage/future-dated stray rows). Every
# loaded council needs an explicit entry, even a clean one, so this stays a
# verified transcription rather than a silent "no issue" default.
#
# The London-pilot entries below keep their original DB-verified row/£
# figures (queried directly against SpendTransaction, not paraphrased from
# a comment) except hackney/richmond-upon-thames/tower-hamlets, which
# gained a genuinely new caveat from their config comment that the old
# README-table method never covered.
#
# Entries tagged `# REVIEW` are a judgment call worth a second look --
# ambiguous wording in the source comment about whether something is a
# confirmed data-quality issue or a legitimate/already-handled case.
#
# has_data_quality_issue, detail_text
COVERAGE_FIXTURE: dict[str, tuple[bool, str]] = {
    "adur": (False, ""),
    "amber-valley": (False, ""),
    "arun": (False, ""),
    "ashfield": (False, ""),
    "ashford": (
        True,
        "supplier-spend-july-23-september-23.xlsx is a mislabelled cumulative "
        "dump (12,054 rows, Jan-Sep 2023) that duplicates rows already "
        "published in the Jan-Mar23 and Apr-Jun23 files; it's kept because "
        "it's the only source for the genuine Jul-Sep23 quarter, so the "
        "overlapping rows inflate a naive sum. 2024/25 Q2-Q4 and 2025/26 Q1 "
        "are also missing pending a fetchable source.",
    ),
    "babergh": (False, ""),
    "barnet": (False, ""),
    "barnsley": (False, ""),
    "basildon": (False, ""),
    "bassetlaw": (False, ""),
    "bath-and-north-east-somerset": (False, ""),
    "bedford": (
        True,
        "Jul-Aug 2024 rows are missing; the source page's earliest file is Sep-2024.",
    ),
    "bexley": (False, ""),
    "birmingham": (False, ""),
    "blaby": (
        True,
        "About 1% of rows (8 file-pairs) are late-posted transactions the "
        "council's own extract includes in both the closing and the following "
        "month's file, inflating a naive sum; no single file is a clean "
        "duplicate to prune.",
    ),
    # REVIEW: ~1% late-posted rows counted in both closing/following-month
    # files -- confirmed inflation or legitimate re-listing?
    "blackpool": (False, ""),
    "bolsover": (False, ""),
    "bolton": (False, ""),
    "boston": (False, ""),
    "bournemouth-christchurch-poole": (False, ""),
    "bracknell-forest": (False, ""),
    "bradford": (
        True,
        "3 months (04.2025, 05.2025, 02.2026) have Supplier Name 100% blank "
        "(the mandatory beneficiary field), so those files are dropped "
        "entirely. Separately, 10,359 of 10,643 rows in "
        "09.2025 duplicate the Sep tail of the mislabelled '07.2025' file "
        "(which actually spans Jul-Sep 2025); 09.2025 is kept anyway for its "
        "284 unique late-Sep rows, so the overlap inflates a naive sum.",
    ),
    "braintree": (False, ""),
    "brent": (False, ""),
    "brentwood": (
        True,
        "No source data exists before Feb-2021; the pre-2021 DataShare portal "
        "(opendata.brentwood.gov.uk) is dead.",
    ),
    "brighton-and-hove": (False, ""),
    "bristol": (False, ""),
    "broadland": (False, ""),
    "bromley": (False, ""),
    "bromsgrove": (
        True,
        "Around 720 genuinely blank-supplier purchase-card rows (2012-2015, "
        '"GPC Purchases" entries) are dropped as a real source gap, not a '
        "parse failure. january-2024.csv also has 29 rows with a corrupted "
        '"10.0.2024" date dropped for the same reason.',
    ),
    "broxtowe": (False, ""),
    "buckinghamshire": (
        True,
        "Amounts are VAT-inclusive (gross) for Apr2020-Oct2022 and net "
        "afterward, with no VAT column in either era to reconcile the two, so "
        "totals/trends spanning the transition mix gross and net figures.",
    ),
    # REVIEW: gross/net VAT-basis mismatch across eras isn't a
    # coverage/duplicate issue but does affect displayed-amount comparability
    "burnley": (False, ""),
    "bury": (
        True,
        "No source data exists for Jul-2024; the earliest available file is Aug-2024.",
    ),
    "cambridge": (False, ""),
    "camden": (False, ""),
    "cannock-chase": (False, ""),
    "canterbury": (False, ""),
    "castle-point": (False, ""),
    "central-bedfordshire": (
        True,
        "No main-CSV source data exists for Aug 2025-Feb 2026; only PCard "
        "data (excluded from this stream) was published for those months.",
    ),
    "charnwood": (False, ""),
    "chelmsford": (
        True,
        "No source data for 2020-03, 2020-06, 2020-07, or 2020-08 (not published).",
    ),
    "cheltenham": (False, ""),
    "cherwell": (
        True,
        "No scrapeable history before Apr 2020; the archive page for earlier "
        "data returns a 403 across live and scripted access alike.",
    ),
    "cheshire-east": (
        True,
        "No source data before 2018/19 (2016/17 and 2017/18 were not published).",
    ),
    "cheshire-west-and-chester": (
        True,
        "No source data for 2021-22 Q1 (never published).",
    ),
    "chesterfield": (
        True,
        "No source data for March 2024 (no CSV or PDF on the source page).",
    ),
    "chichester": (False, ""),
    "chorley": (False, ""),
    "city-of-london": (False, ""),
    "colchester": (
        True,
        "No source data for 2019-06 or 2026-05 (auth-walled SharePoint share "
        "links). Separately, ~9,600 of 144,000 rows are dropped for genuinely "
        "blank Payment Date.",
    ),
    "cornwall": (False, ""),
    "cotswold": (False, ""),
    "coventry": (
        True,
        "Confirmed duplicate transactions (same Transaction No, not distinct "
        "spend) account for 6.6% of curated SUM(AMOUNT_GBP), £322,678,955.79.",
    ),
    "crawley": (False, ""),
    "croydon": (False, ""),
    "cumberland": (
        True,
        "Cumberland's 'support related payments to individuals' series "
        "(direct payments, foster and adoption placements) carries no "
        "supplier-name column, so every row fails the beneficiary-name filter "
        "and the whole series is not ported; this spend category is absent "
        "from displayed totals.",
    ),
    # REVIEW: whole 'support related payments to individuals' series
    # excluded for lacking a supplier-name column -- scope exclusion or
    # real gap?
    "dacorum": (False, ""),
    "darlington": (False, ""),
    "dartford": (
        True,
        "No source data for Apr 2020-May 2021 or Aug/Sep/Nov 2021 (published "
        "PDF-only, no machine-readable file); earliest included month is Jun "
        "2021.",
    ),
    "derby": (False, ""),
    "derbyshire-dales": (False, ""),
    "doncaster": (
        True,
        "No machine-readable source data before Oct 2023; Apr 2022-Sep 2023 "
        "and earlier were published PDF-only.",
    ),
    "dorset": (False, ""),
    "dover": (False, ""),
    "dudley": (False, ""),
    "durham": (
        True,
        "No source data for December 2024: the only published file for that "
        "month is a purchase-card export, excluded per project-wide scope "
        "policy.",
    ),
    "ealing": (False, ""),
    "east-cambridgeshire": (
        True,
        "No source data for June 2023.",
    ),
    "east-devon": (False, ""),
    "east-hampshire": (
        True,
        "No machine-readable source data for 2016 or March 2026 (PDF-only on the source page).",
    ),
    "east-hertfordshire": (
        True,
        "No source data for 2019-2021 (no published report at all). "
        "Separately, 16 weekly files (Mar-Oct 2017) never existed at the "
        "source, one 2016 week is password-protected, and one 2024-02 week "
        "sits behind an internal login wall.",
    ),
    "east-lindsey": (
        True,
        "No source data for May 2017 (gap in the council's invoice stream).",
    ),
    "east-riding-of-yorkshire": (
        True,
        "2,106 batch/grant rows in P11 Feb 2021 are stamped with an "
        "impossible date (29/02/2021, not a leap year) and dropped as "
        "unparseable, so those rows' amounts are missing from displayed "
        "totals.",
    ),
    "east-staffordshire": (
        True,
        "2011Q3.csv and 2012Q4.csv genuinely overlap by ~150 rows in Nov-Dec "
        "2011 (kept as published), double-counting that overlap in the "
        "displayed total. Separately, 2010Q1.csv has no date column at all; "
        "~643 rows drop entirely for missing date.",
    ),
    "east-suffolk": (
        True,
        "Every one of February 2025's 824 rows is stamped with an implausible "
        "2-digit year ('29') instead of the real period, a source-side typo "
        "kept verbatim rather than clamped.",
    ),
    "eastleigh": (False, ""),
    "elmbridge": (False, ""),
    "epping-forest": (False, ""),
    "epsom-and-ewell": (
        True,
        "No source data for January 2020 (both PDF and CSV 404 on the server).",
    ),
    "erewash": (
        True,
        "About 30 rows (~1.2% of total) are identical duplicates recurring "
        "across adjacent-month files, mostly recurring temp-accommodation "
        "invoices sharing a date+amount; the source re-lists them and they're "
        "kept as-is, so a naive sum double-counts them.",
    ),
    # REVIEW: ~1.2% cross-file repeats described by source as re-listed,
    # not distinct spend -- confirmed duplicate or legitimate re-list?
    "exeter": (False, ""),
    "fareham": (False, ""),
    "folkestone-hythe": (
        True,
        "No source data exists for 2015 (the council's listing/file pages 403 "
        "on every request); coverage starts 2016-01.",
    ),
    "forest-of-dean": (False, ""),
    "fylde": (
        True,
        "2025-06 and 2026-06 data could not be recovered -- both collided on "
        "disk under the same generic upload filename as the 2026-07 file, and "
        "only 2026-07 was kept.",
    ),
    "gedling": (
        True,
        "No source data was published for the Apr-Jun 2024 quarter.",
    ),
    "gloucester": (False, ""),
    "gosport": (False, ""),
    "gravesham": (False, ""),
    "great-yarmouth": (False, ""),
    "greenwich": (
        True,
        "PDF-only gaps exist for Jul 2017-Jun 2018 and Jul-Dec 2018, with no "
        "machine-readable source available for those periods.",
    ),
    "guildford": (False, ""),
    "hackney": (
        True,
        "Jan 2013-Mar 2016 (plus a stray Nov 2016 file) use a month-only "
        "layout with no payment date and are omitted as undateable, so "
        "coverage effectively starts Apr 2016.",
    ),
    "halton": (False, ""),
    "hammersmith-and-fulham": (
        True,
        "Only Q4 2023-24 onward is covered; the council publishes no earlier spend-over-500 files.",
    ),
    "harborough": (False, ""),
    "haringey": (False, ""),
    "harlow": (False, ""),
    "harrow": (
        True,
        "36 rows (£2,754) predate Harrow's first published file (2022-01).",
    ),
    "hart": (False, ""),
    "hartlepool": (False, ""),
    "hastings": (False, ""),
    "havant": (False, ""),
    "havering": (
        True,
        "1,457 rows (£3,152,405) predate Havering's first published file (2010-12).",
    ),
    "herefordshire": (False, ""),
    "hertsmere": (
        True,
        "over-500-disclosure-july-2021.xls duplicates ~625 rows already "
        "counted in the May/June standalone files; it's kept (not pruned) "
        "because it's the only source for July's own rows, so the displayed "
        "total double-counts those ~625 rows.",
    ),
    "high-peak": (False, ""),
    "hillingdon": (False, ""),
    "hinckley-and-bosworth": (
        True,
        "Jan-Dec 2019 files were pulled from the source page and no longer "
        "link; pre-2019 months use a "
        "decommissioned URL scheme that also 404s. Coverage now starts "
        "January 2020.",
    ),
    "horsham": (False, ""),
    "hounslow": (False, ""),
    "huntingdonshire": (
        True,
        "Jul-Sep and Oct-Dec 2018 report every amount as negative -- a "
        "ledger-export convention for that half-year -- "
        "retained as published, so displayed totals for that period reflect "
        "the sign flip.",
    ),
    "hyndburn": (False, ""),
    "ipswich": (False, ""),
    "isle-of-wight": (False, ""),
    "isles-of-scilly": (False, ""),
    "islington": (
        True,
        "388 rows (£2,023,047) predate Islington's first published file (2019-09).",
    ),
    "kensington-and-chelsea": (False, ""),
    "kings-lynn-and-west-norfolk": (False, ""),
    "kingston-upon-hull": (
        True,
        "13,533 rows (0.83% of raw) drop from the September 2025 file because "
        'its month column spells "Sept" with 4 letters, a format no date '
        "pattern can cover without also mis-parsing other months. Coverage "
        "also ends Dec-2024: the site's 2025/2026 category listing pages have "
        "404'd since Feb-2026 with no replacement URL found, so Jan 2025 "
        "onward isn't published pending the council republishing.",
    ),
    "kingston-upon-thames": (
        True,
        "No source data exists for Jun 2011-Mar 2020, and June 2020 is also "
        "missing (the site's own link mis-points at June 2021). May 2026 has "
        "not yet been published.",
    ),
    "kirklees": (False, ""),
    "knowsley": (False, ""),
    "lambeth": (
        True,
        "Lambeth's earliest 2010-2011 files are supplier totals with no date "
        "column at all, so those rows are dropped entirely and don't appear "
        "in totals or the displayed date range.",
    ),
    # REVIEW: earliest 2010-2011 files structurally lack a date column --
    # schema limitation or real gap?
    "leicester": (False, ""),
    "lewisham": (
        True,
        "A handful of months have dead source links and are omitted entirely, "
        "so those months are missing from the displayed date range.",
    ),
    # REVIEW: some months have dead source links, omitted -- genuinely
    # unrecoverable or just needs a link fix?
    "lichfield": (False, ""),
    "lincoln": (False, ""),
    "liverpool": (
        True,
        "Jan-May 2026 is published PDF-only so far (no spreadsheet yet).",
    ),
    "luton": (
        True,
        "No data exists for years before Jan 2024: the council took down "
        "earlier years' pages (404s).",
    ),
    "maidstone": (
        False,
        "",
    ),
    # REVIEW: dead .mht mirrors / stray 2019 PDF excluded -- unclear if
    # 2019 has any other real source coverage
    "maldon": (False, ""),
    "malvern-hills": (False, ""),
    "mansfield": (
        True,
        "2013-14 to 2019-20 and FY2022-23 supplier-spend are published "
        "PDF-only (no spreadsheet) and omitted.",
    ),
    "medway": (False, ""),
    "melton": (
        True,
        "About 43 rows (~£53k, 0.14% of curated total) are duplicate invoices "
        "double-counted where adjacent period files' date ranges overlap; "
        "spread across many file pairs rather than one superseded file, so "
        "they're left in rather than pruned.",
    ),
    "merton": (
        True,
        "743 rows (£10,452,031) predate Merton's first published file (2010-08).",
    ),
    "mid-devon": (
        True,
        "The site keeps only a rolling ~2-year window, so earlier months "
        "already 404; December 2024 itself is also missing.",
    ),
    "mid-suffolk": (False, ""),
    "mid-sussex": (False, ""),
    "middlesbrough": (
        True,
        "No CSV was ever published for Sept 2013, Feb 2016, or Aug 2021 (PDF only).",
    ),
    "milton-keynes": (
        True,
        "Apr 2019-Mar 2020 data is no longer available: the source archive "
        "page now starts at 2020/21 and the older files 404.",
    ),
    "mole-valley": (False, ""),
    "new-forest": (
        True,
        "About 0.1% of rows are duplicate transactions from adjacent-month "
        "files' overlapping date ranges (spread thin, not one superseded "
        "file). Separately, roughly £1bn of the total is Treasury 'Loans Out' "
        "money-market-fund placements, not real supplier spend, reproduced "
        "faithfully from the same export rather than filtered out.",
    ),
    "newark-and-sherwood": (
        True,
        "No file was ever published for Q4 FY2023-24 (Jan-Mar 2024).",
    ),
    "newcastle-under-lyme": (False, ""),
    "newcastle-upon-tyne": (
        True,
        "November 2025 has no published file on the source page.",
    ),
    "newham": (False, ""),
    "north-devon": (False, ""),
    "north-east-derbyshire": (False, ""),
    "north-east-lincolnshire": (False, ""),
    "north-hertfordshire": (
        True,
        "No CSV or PDF has been published for 2024-2025: the council pulled "
        "it site-side ('errors have been found').",
    ),
    "north-kesteven": (False, ""),
    "north-norfolk": (False, ""),
    "north-northamptonshire": (False, ""),
    "north-somerset": (False, ""),
    "north-tyneside": (False, ""),
    "north-warwickshire": (False, ""),
    "north-west-leicestershire": (
        True,
        "2010-11 through 2019-20 landing pages are now 410 Gone (removed by "
        "the council) and Apr-Aug 2024 has no published file anywhere. "
        "From 2023-24 on, the "
        "source's gross-amount column also repeats the whole invoice total on "
        "every split line of a multi-line invoice, so the mapped AMOUNT_GBP "
        "overstates spend for those invoices; left as published rather than "
        "corrected.",
    ),
    "north-yorkshire": (
        True,
        "History starts Apr 2022 -- older pre-2022 files are gone from the "
        "source (404 on the current hub) and aren't recoverable.",
    ),
    "norwich": (False, ""),
    "nottingham": (False, ""),
    "nuneaton-and-bedworth": (
        True,
        "Only 2023/24 onward is available; earlier years require emailing the "
        "council directly, so no scrapeable history exists before then.",
    ),
    "oadby-and-wigston": (False, ""),
    "oldham": (False, ""),
    "oxford": (False, ""),
    "pendle": (False, ""),
    "peterborough": (False, ""),
    "plymouth": (False, ""),
    "portsmouth": (False, ""),
    "preston": (False, ""),
    "reading": (
        True,
        "April-June 2019 and Jul-Sept 2019 files are over 98% month-only "
        "dates and are dropped as unparseable, leaving only a few hundred "
        "day-level rows in each; Jan-March 2019 is entirely month-only and "
        "dropped in full.",
    ),
    "redbridge": (
        True,
        "1,121 rows (£24,679,100) predate Redbridge's first published file "
        "(2010-03); a further 4 rows (£9,594) are dated 2027 or later, past "
        "the source's actual mid-2026 coverage. Both are source date-entry "
        "typos (real supplier + amount, implausible year), retained verbatim "
        "rather than clamped.",
    ),
    "redcar-and-cleveland": (False, ""),
    "redditch": (False, ""),
    "reigate-and-banstead": (False, ""),
    "ribble-valley": (
        True,
        "No source data published for Apr 2015-Mar 2017; the council's own "
        "archive skips straight from 2014/15 to 2017/18.",
    ),
    "richmond-upon-thames": (
        True,
        "No source file exists for January 2020; the source page's January "
        "link actually points at the February 2020 file.",
    ),
    "rochdale": (False, ""),
    "rochford": (False, ""),
    "rossendale": (False, ""),
    "rother": (False, ""),
    "rotherham": (
        True,
        "No spend-over-£500 data exists before April 2020; earlier records "
        "are procurement-card only, which is out of scope.",
    ),
    "rugby": (False, ""),
    "runnymede": (
        True,
        "No source file actually holds May 2021 data.",
    ),
    "rushcliffe": (False, ""),
    "rushmoor": (False, ""),
    "rutland": (False, ""),
    "salford": (False, ""),
    "sandwell": (False, ""),
    "sefton": (False, ""),
    "sevenoaks": (
        True,
        "Aug-Nov 2010 (the first 4 months published) have no date column at "
        "all, so those rows are undateable and dropped entirely.",
    ),
    "sheffield": (False, ""),
    "shropshire": (False, ""),
    "slough": (False, ""),
    "solihull": (
        True,
        "No data before 2019-05; earlier months (2013-2019) are dead links no "
        "longer served by the source, in either PDF or CSV.",
    ),
    "somerset": (
        True,
        "Somerset's own published caveat: Q1/Q2 2023-24 data extraction from "
        "the legacy finance system was incomplete at publication time, so "
        "those quarters' totals may understate actual spend.",
    ),
    "south-cambridgeshire": (False, ""),
    "south-derbyshire": (False, ""),
    "south-gloucestershire": (
        True,
        "~7.6k rows across three 2010 files (Apr, May, Jun) publish no "
        "payment-date column at all and are dropped by the required-DATE "
        "filter.",
    ),
    "south-hams": (
        True,
        "FY2018/19 (Mar-2018 to Apr-2019) is absent from the source webapp entirely.",
    ),
    "south-holland": (
        True,
        "No file (CSV or XML) was published for July 2018.",
    ),
    "south-kesteven": (False, ""),
    "south-norfolk": (False, ""),
    "south-oxfordshire": (False, ""),
    "south-ribble": (False, ""),
    "southampton": (False, ""),
    "southend-on-sea": (False, ""),
    "southwark": (
        True,
        "Pre-2015 2-column .xls files (vendor and amount only, no date) are "
        "excluded entirely since rows without a date can't be curated, "
        "narrowing the coverage available from Southwark's early years.",
    ),
    # REVIEW: pre-2015 2-column .xls files (no date) excluded entirely --
    # narrows early-years coverage, worth confirming no date can be
    # recovered
    "spelthorne": (
        True,
        "Jan 2024 is PDF-only, with no CSV or xlsx published that month.",
    ),
    "st-albans": (
        True,
        "No file was published for November 2021.",
    ),
    "st-helens": (
        True,
        "2022-11 and 2026-03 are PDF-only, with no xlsx published for either month.",
    ),
    "stafford": (False, ""),
    "staffordshire-moorlands": (False, ""),
    "stevenage": (False, ""),
    "stockport": (
        True,
        "No source data is reachable for Jan 2013-Jan 2017 (dead hosting "
        "backend, 503s unconditionally); the earliest available file is Feb "
        "2017.",
    ),
    "stoke-on-trent": (False, ""),
    "stratford-on-avon": (False, ""),
    "stroud": (
        True,
        "161 rows are literal same-file duplicates (identical Transaction "
        "Number repeated) and remain in the totals, inflating a naive sum.",
    ),
    "sunderland": (False, ""),
    "surrey-heath": (False, ""),
    "sutton": (
        True,
        "838 rows (£8,700,673) predate Sutton's first published file "
        "(2018-03); a further 1 row (£30,000) is dated 2027 or later, past "
        "the source's actual coverage.",
    ),
    "swale": (False, ""),
    "swindon": (False, ""),
    "tameside": (False, ""),
    "tamworth": (False, ""),
    "tandridge": (False, ""),
    "teignbridge": (
        True,
        "Only a rolling ~12-month window (Jul 2025 on) is published at all; "
        "within that, Jul-Oct 2025 exist only as PDF and are excluded as not "
        "machine-readable.",
    ),
    "telford-and-wrekin": (False, ""),
    "tendring": (
        True,
        "2016-17 and 2017-18 files 404 upstream (dead links); the earliest "
        "available file is 2018-19.",
    ),
    "test-valley": (
        True,
        "No CSV was published prior to Jan 2014.",
    ),
    "tewkesbury": (False, ""),
    "thanet": (
        True,
        "Nov 2013 is excluded entirely: the published file is a legacy .xls "
        "served with a .csv extension that would parse incorrectly, leaving a "
        "one-month gap.",
    ),
    "three-rivers": (
        True,
        "No source data exists for FY2022-2023 (PDF-only, no xlsx counterpart published).",
    ),
    "thurrock": (False, ""),
    "tonbridge-and-malling": (False, ""),
    "torbay": (False, ""),
    "tower-hamlets": (
        True,
        "A few hundred malformed, shifted-column rows are dropped from the parse every run.",
    ),
    "trafford": (False, ""),
    "tunbridge-wells": (False, ""),
    "uttlesford": (False, ""),
    "vale-of-white-horse": (False, ""),
    "wakefield": (
        True,
        "No CSV/xlsx data was published for 2021-22 Q4 (PDF-only on the source site, excluded).",
    ),
    "walsall": (False, ""),
    "waltham-forest": (False, ""),
    "wandsworth": (False, ""),
    "warrington": (False, ""),
    "warwick": (False, ""),
    "watford": (False, ""),
    "waverley": (False, ""),
    "wealden": (False, ""),
    "welwyn-hatfield": (
        True,
        "Source only keeps a rolling ~12-month window of files live (older ids 404).",
    ),
    # REVIEW: source keeps only a rolling ~12-month window -- unclear if
    # ingested history is capped at that window or built up from
    # snapshots over time
    "west-devon": (False, ""),
    "west-lancashire": (False, ""),
    "west-lindsey": (False, ""),
    "west-northamptonshire": (False, ""),
    "west-oxfordshire": (False, ""),
    "west-suffolk": (False, ""),
    "westminster": (False, ""),
    "westmorland-and-furness": (
        True,
        "About 0.15% of rows (mostly in one Support Related Payments file) "
        "are literal duplicate source lines left in rather than deduped, "
        "inflating a naive sum by that amount.",
    ),
    "wigan": (False, ""),
    "winchester": (False, ""),
    "windsor-and-maidenhead": (False, ""),
    "wirral": (
        True,
        "The December 2025 file is missing its Paid Date column, shifting "
        "every field left; roughly 4,985 of 4,987 rows drop on a null amount "
        "before any date check runs.",
    ),
    "woking": (False, ""),
    "wokingham": (False, ""),
    "wolverhampton": (
        True,
        "No spend-over-£500 report was published for Feb 2026 or Mar 2026.",
    ),
    "worcester": (
        True,
        "No CSV data exists for Jun 2022 (published PDF-only).",
    ),
    "worthing": (False, ""),
    "wychavon": (
        True,
        "No source data could be recovered for 2023-08 or 2024-12 through "
        "2025-05 inclusive, despite walking every Wayback Machine snapshot "
        "back to 2017.",
    ),
    "wyre": (False, ""),
    "wyre-forest": (False, ""),
    "york": (False, ""),
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
