# Generated manually for the operational-unit normalization.

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("base", "0002_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="OperationalUnit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, blank=True, null=True, verbose_name="Created At")),
                ("is_active", models.BooleanField(default=True, verbose_name="Is Active")),
                ("name", models.CharField(max_length=100, verbose_name="Name")),
                ("short_name", models.CharField(max_length=30, verbose_name="Short name")),
                ("code", models.CharField(max_length=30, verbose_name="Code")),
                ("type", models.CharField(choices=[("SEDE", "SEDE"), ("NEGOZI", "NEGOZI")], max_length=10, verbose_name="Type")),
                ("company_id", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="operational_units", to="base.company", verbose_name="Company")),
                ("created_by", models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL, verbose_name="Created By")),
                ("modified_by", models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="operationalunit_modified_by", to=settings.AUTH_USER_MODEL, verbose_name="Modified By")),
            ],
            options={"verbose_name": "Operational unit", "verbose_name_plural": "Operational units"},
        ),
        migrations.AddConstraint(
            model_name="operationalunit",
            constraint=models.UniqueConstraint(fields=("company_id", "type", "code"), name="unique_operational_unit_code_per_company_type"),
        ),
        migrations.AddConstraint(
            model_name="operationalunit",
            constraint=models.UniqueConstraint(fields=("company_id", "type", "short_name"), name="unique_operational_unit_short_name_per_company_type"),
        ),
    ]
