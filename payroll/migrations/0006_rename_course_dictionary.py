from django.db import migrations


def rename_course(apps, schema_editor):
    Dictionary = apps.get_model("payroll", "PayslipDizionario")
    old = "CORSO AI DIPENDENTI"
    new = "CORSI AI DIPENDENTI"
    for row in Dictionary.objects.using(schema_editor.connection.alias).all():
        fields = []
        if row.codice_tipo_orario == old:
            row.codice_tipo_orario = new
            fields.append("codice_tipo_orario")
        if old in (row.tipi_app_ammessi or []):
            row.tipi_app_ammessi = list(dict.fromkeys(
                new if kind == old else kind for kind in row.tipi_app_ammessi
            ))
            fields.append("tipi_app_ammessi")
        if fields:
            row.save(update_fields=fields)


class Migration(migrations.Migration):
    dependencies = [("payroll", "0005_attendance_dictionary_equivalences")]

    operations = [migrations.RunPython(rename_course, migrations.RunPython.noop)]
