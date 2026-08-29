from django.contrib.postgres.operations import TrigramExtension
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("spend", "0001_initial"),
    ]

    operations = [
        TrigramExtension(),
        migrations.RunSQL(
            sql=(
                "CREATE INDEX spend_spendtransaction_beneficiary_name_trgm "
                "ON spend_spendtransaction USING GIN (beneficiary_name gin_trgm_ops);"
            ),
            reverse_sql="DROP INDEX spend_spendtransaction_beneficiary_name_trgm;",
        ),
    ]
