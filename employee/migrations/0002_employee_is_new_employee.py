from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("employee", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE employee_employee
                ADD COLUMN IF NOT EXISTS is_new_employee boolean NOT NULL DEFAULT TRUE;
            """,
            reverse_sql="""
                ALTER TABLE employee_employee
                DROP COLUMN IF EXISTS is_new_employee;
            """,
        ),
    ]
