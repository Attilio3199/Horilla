from django.db import migrations


def set_existing_employees_not_new(apps, schema_editor):
    Employee = apps.get_model("employee", "Employee")
    Employee.objects.filter(is_new_employee=True).update(is_new_employee=False)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("employee", "0002_employee_is_new_employee"),
    ]

    operations = [
        migrations.RunPython(set_existing_employees_not_new, noop),
    ]
