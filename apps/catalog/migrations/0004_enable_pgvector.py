# Manual migration to enable pgvector extension before any VectorField usage.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0003_add_stock_quantity'),
    ]

    operations = [
        migrations.RunSQL(
            sql="CREATE EXTENSION IF NOT EXISTS vector",
            reverse_sql="DROP EXTENSION IF EXISTS vector",
        ),
    ]
