from django.test import TestCase

from base.turni_views import _extract_inserts, _parse_create_table, _source_columns


class TurniImportTests(TestCase):
    def test_preferenza_is_not_created_or_imported(self):
        ddl = """
            CREATE TABLE `turni_creati` (
              `id` bigint(20) NOT NULL AUTO_INCREMENT,
              `Descrizione` varchar(100) NOT NULL,
              `Preferenza` tinyint(1) NOT NULL DEFAULT 0,
              `Annotazioni` varchar(100) DEFAULT NULL,
              PRIMARY KEY (`id`)
            ) ENGINE=InnoDB;
        """
        dump = ddl + """
            INSERT INTO `turni_creati` VALUES
            (1,'Turno, mattina',1,NULL),(2,'Turno serale',0,'nota');
        """

        converted_ddl = _parse_create_table(ddl)
        inserts = _extract_inserts(dump, "turni_creati", _source_columns(ddl))

        self.assertNotIn('"Preferenza"', converted_ddl)
        self.assertEqual(
            inserts,
            [
                'INSERT INTO "_turni_creati" ("id", "Descrizione", "Annotazioni") '
                "VALUES (1,'Turno, mattina',NULL),(2,'Turno serale','nota');"
            ],
        )
