from django.db import migrations, models


def populate_equivalences(apps, schema_editor):
    Dictionary = apps.get_model("payroll", "PayslipDizionario")
    for row in Dictionary.objects.using(schema_editor.connection.alias).all():
        category = (row.codice_tipo_orario or "").strip()
        try:
            voice = int(row.cod_voce)
        except (ValueError, TypeError):
            voice = None
        if voice in {302, 335, 303, 336, 337, 304}:
            row.tipi_app_ammessi = ["FERIE", "ROL"]
        elif voice == 300:
            row.tipi_app_ammessi = ["LAVORATO", "SMART WORKING", "CORSO AI DIPENDENTI"]
        else:
            row.tipi_app_ammessi = [category] if category else []
        row.save(update_fields=["tipi_app_ammessi"])


class Migration(migrations.Migration):
    dependencies = [("payroll", "0004_contractlevel")]

    operations = [
        migrations.AddField(
            model_name="payslipdizionario",
            name="tipi_app_ammessi",
            field=models.JSONField(blank=True, default=list,
                verbose_name="Tipi app ammessi",
                help_text="Tipi di turno che questa voce del cedolino può coprire."),
        ),
        migrations.RunPython(populate_equivalences, migrations.RunPython.noop),
        migrations.DeleteModel(name="PayslipControlloRegolaDestinazione"),
        migrations.DeleteModel(name="PayslipControlloRegola"),
    ]
