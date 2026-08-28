from django.db import migrations
from django.utils.text import slugify

# Source: ONS Open Geography Portal, "Local Authority Districts (December
# 2024) Names and Codes in the UK" (LAD24CD/LAD24NM), filtered to E09
# (London borough) codes, excluding E09000001 City of London (not a
# borough). Downloaded 2026-08-25 from:
# https://open-geography-portalx-ons.hub.arcgis.com/api/download/v1/items/984b3f485d1a4c0f9d9e51617cafc224/csv?layers=0
# Deliberately not reusing the sibling data repo's docs/local-authorities.csv
# (confirmed stale, pre-2023 reorg) per docs/ARCHITECTURE.md.
LONDON_BOROUGHS = [
    ("E09000002", "Barking and Dagenham"),
    ("E09000003", "Barnet"),
    ("E09000004", "Bexley"),
    ("E09000005", "Brent"),
    ("E09000006", "Bromley"),
    ("E09000007", "Camden"),
    ("E09000008", "Croydon"),
    ("E09000009", "Ealing"),
    ("E09000010", "Enfield"),
    ("E09000011", "Greenwich"),
    ("E09000012", "Hackney"),
    ("E09000013", "Hammersmith and Fulham"),
    ("E09000014", "Haringey"),
    ("E09000015", "Harrow"),
    ("E09000016", "Havering"),
    ("E09000017", "Hillingdon"),
    ("E09000018", "Hounslow"),
    ("E09000019", "Islington"),
    ("E09000020", "Kensington and Chelsea"),
    ("E09000021", "Kingston upon Thames"),
    ("E09000022", "Lambeth"),
    ("E09000023", "Lewisham"),
    ("E09000024", "Merton"),
    ("E09000025", "Newham"),
    ("E09000026", "Redbridge"),
    ("E09000027", "Richmond upon Thames"),
    ("E09000028", "Southwark"),
    ("E09000029", "Sutton"),
    ("E09000030", "Tower Hamlets"),
    ("E09000031", "Waltham Forest"),
    ("E09000032", "Wandsworth"),
    ("E09000033", "Westminster"),
]


def load_boroughs(apps, schema_editor):
    Council = apps.get_model("councils", "Council")
    Council.objects.bulk_create(
        Council(name=name, slug=slugify(name), gss_code=gss_code)
        for gss_code, name in LONDON_BOROUGHS
    )


def unload_boroughs(apps, schema_editor):
    Council = apps.get_model("councils", "Council")
    Council.objects.filter(gss_code__in=[code for code, _ in LONDON_BOROUGHS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("councils", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(load_boroughs, unload_boroughs),
    ]
