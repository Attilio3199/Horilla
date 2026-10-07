from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    """Keep the simple-history table aligned with employee work information."""

    dependencies = [
        ("employee", "0005_employeeworkinformation_operational_unit"),
        ("base", "0003_operationalunit"),
    ]

    operations = [
        migrations.AddField(
            model_name="historicalemployeeworkinformation",
            name="operational_unit_id",
            field=models.ForeignKey(
                blank=True,
                db_constraint=False,
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="+",
                to="base.operationalunit",
                verbose_name="Operational unit",
            ),
        ),
    ]
