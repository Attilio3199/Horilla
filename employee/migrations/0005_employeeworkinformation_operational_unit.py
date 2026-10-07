from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("base", "0003_operationalunit"),
        ("employee", "0004_auth_user_is_new_employee_default"),
    ]

    operations = [
        migrations.AddField(
            model_name="employeeworkinformation",
            name="operational_unit_id",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="employee_work_informations", to="base.operationalunit", verbose_name="Operational unit"),
        ),
    ]
