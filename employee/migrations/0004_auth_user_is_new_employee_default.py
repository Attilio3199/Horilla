from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("employee", "0003_set_existing_employees_not_new"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = 'auth_user'
                          AND column_name = 'is_new_employee'
                    ) THEN
                        ALTER TABLE auth_user
                        ALTER COLUMN is_new_employee SET DEFAULT TRUE;
                    END IF;
                END $$;
            """,
            reverse_sql="""
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = 'auth_user'
                          AND column_name = 'is_new_employee'
                    ) THEN
                        ALTER TABLE auth_user
                        ALTER COLUMN is_new_employee DROP DEFAULT;
                    END IF;
                END $$;
            """,
        ),
    ]
