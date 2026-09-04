from django.db import migrations


class Migration(migrations.Migration):
    """Disable GIN fastupdate on the trigram index.

    With fastupdate on, inserts land in an unordered pending list that's
    only merged into the main index on vacuum/analyze or once it grows past
    gin_pending_list_limit. This loader's write pattern -- delete then
    bulk-insert a whole council's rows per run -- is exactly the bursty
    shape that caused a real GitLab outage via pending-list overflow.
    fastupdate=off forces every insert straight into the main structure,
    removing the pending list (and its overflow failure mode) entirely.
    """

    dependencies = [
        ("spend", "0002_beneficiary_name_trgm_index"),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                "ALTER INDEX spend_spendtransaction_beneficiary_name_trgm SET (fastupdate = off);"
            ),
            reverse_sql=(
                "ALTER INDEX spend_spendtransaction_beneficiary_name_trgm SET (fastupdate = on);"
            ),
        ),
    ]
