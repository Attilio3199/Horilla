"""Test cases for payroll."""

from io import BytesIO
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from unittest import TestCase as UnitTestCase

from django.test import SimpleTestCase, TestCase
from openpyxl import Workbook, load_workbook

from employee.models import Employee
from payroll.services.payment_file import (
    fill_payment_file,
    payment_file_has_existing_values,
)
from payroll.views.component_views import _sync_employee_payroll_identity


class AttendanceControlTests(UnitTestCase):
    def _run_check(self, rows, shifts):
        from payroll.views.component_views import _build_risultati_for_export

        mappings = [
            SimpleNamespace(id=1, cod_voce="0302", codice_tipo_orario="FERIE",
                            tipo_ora="previsionale", tipi_app_ammessi=["FERIE", "ROL"]),
            SimpleNamespace(id=2, cod_voce="0303", codice_tipo_orario="ROL",
                            tipo_ora="consuntivo", tipi_app_ammessi=["FERIE", "ROL"]),
            SimpleNamespace(id=3, cod_voce="0300", codice_tipo_orario="LAVORATO",
                            tipo_ora="consuntivo", tipi_app_ammessi=[
                                "LAVORATO", "SMART WORKING", "CORSO AI DIPENDENTI"]),
        ]
        employees = [{"cod_dip": "B1", "lavoratore": "Test", "matricola": "M1"}]
        employee_qs = MagicMock()
        employee_qs.exclude.return_value.exclude.return_value.values.return_value.distinct.return_value.order_by.return_value = employees * 2
        presence_qs = MagicMock()
        presence_qs.values.return_value = [
            {"cod_dip": "B1", "cod_voce": voice, **{
                f"day_{day}": Decimal(str(hours)) if day == 1 else None
                for day in range(1, 29)
            }} for voice, hours in rows
        ]
        cursor = MagicMock()
        cursor.description = [(name,) for name in [
            "CODICEPERSONALE", "CODICE_TIPO_ORARIO", "giorno", "ore_cons", "ore_prev"]]
        cursor.fetchall.return_value = [("B1", kind, 1, cons, prev) for kind, cons, prev in shifts]
        module = "payroll.views.component_views"
        with patch(module + ".PayslipDizionario.objects.filter") as dictionary, \
             patch(module + ".PayslipPresenze.objects.filter", side_effect=[employee_qs, presence_qs]), \
             patch(module + "._pg_conn.cursor") as db_cursor:
            dictionary.return_value.order_by.return_value = mappings
            db_cursor.return_value.__enter__.return_value = cursor
            return _build_risultati_for_export(2, 2026, ["B1"])

    def test_duplicate_rows_are_summed_and_employee_checked_once(self):
        results, _, count = self._run_check([(302, 3), (302, 5)], [("FERIE", 0, 8)])
        self.assertEqual(results, [])
        self.assertEqual(count, 1)

    def test_ferie_and_rol_keep_their_own_hour_source(self):
        results, _, _ = self._run_check([(302, 4), (303, 4)],
            [("FERIE", 0, 4), ("ROL", 4, 0)])
        self.assertEqual(results, [])

    def test_smart_work_and_course_are_covered_by_worked_voice(self):
        results, _, _ = self._run_check([(300, 4), (300, 4)],
            [("SMART WORKING", 4, 0), ("CORSO AI DIPENDENTI", 4, 0)])
        self.assertEqual(results, [])

    def test_shared_payslip_hours_are_not_reused(self):
        results, _, _ = self._run_check([(302, 8)],
            [("FERIE", 0, 8), ("ROL", 8, 0)])
        self.assertEqual(len(results[0]["discrepanze"]), 1)
        self.assertEqual(results[0]["discrepanze"][0]["ore_app_non_coperte"], 8)


class EmployeePayrollIdentitySyncTests(TestCase):
    @staticmethod
    def _employee(index, **identity):
        employee = Employee(
            employee_first_name=f"Dipendente {index}",
            email=f"dipendente{index}@example.com",
            phone=f"000{index}",
            **identity,
        )
        Employee.objects.bulk_create([employee])
        return employee

    def test_adds_missing_payroll_code_using_badge(self):
        employee = self._employee(1, badge_id="B001")

        result = _sync_employee_payroll_identity("M001", "B001")

        employee.refresh_from_db()
        self.assertEqual(result, "updated")
        self.assertEqual(employee.codice_paghe, "M001")

    def test_adds_missing_badge_using_payroll_code(self):
        employee = self._employee(2, codice_paghe="M002")

        result = _sync_employee_payroll_identity("M002", "B002")

        employee.refresh_from_db()
        self.assertEqual(result, "updated")
        self.assertEqual(employee.badge_id, "B002")

    def test_replaces_stale_payroll_code_using_badge(self):
        employee = self._employee(5, badge_id="B005", codice_paghe="OLD-M005")

        result = _sync_employee_payroll_identity("M005", "B005")

        employee.refresh_from_db()
        self.assertEqual(result, "updated")
        self.assertEqual(employee.codice_paghe, "M005")

    def test_replaces_stale_badge_using_payroll_code(self):
        employee = self._employee(6, badge_id="OLD-B006", codice_paghe="M006")

        result = _sync_employee_payroll_identity("M006", "B006")

        employee.refresh_from_db()
        self.assertEqual(result, "updated")
        self.assertEqual(employee.badge_id, "B006")

    def test_does_not_overwrite_two_existing_associations(self):
        badge_employee = self._employee(3, badge_id="B003")
        payroll_employee = self._employee(4, codice_paghe="M004")

        result = _sync_employee_payroll_identity("M004", "B003")

        badge_employee.refresh_from_db()
        payroll_employee.refresh_from_db()
        self.assertEqual(result, "conflict")
        self.assertIsNone(badge_employee.codice_paghe)
        self.assertIsNone(payroll_employee.badge_id)

    def test_does_not_create_an_employee_without_a_match(self):
        result = _sync_employee_payroll_identity("M999", "B999")

        self.assertEqual(result, "not_found")
        self.assertFalse(Employee.objects.filter(badge_id="B999").exists())


class PaymentFileServiceTests(SimpleTestCase):
    @staticmethod
    def _workbook_bytes(column_l="acconto esistente", column_m=None):
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Pagamenti"
        sheet["H2"] = "B001"
        sheet["L2"] = column_l
        sheet["M2"] = column_m
        output = BytesIO()
        workbook.save(output)
        return output.getvalue()

    def test_fill_updates_only_column_m(self):
        content = self._workbook_bytes(column_m="vecchio netto")

        result, filled, missing = fill_payment_file(
            content, "pagamenti.xlsx", "Pagamenti", {"B001": 1234.56}
        )

        workbook = load_workbook(BytesIO(result), data_only=False)
        sheet = workbook["Pagamenti"]
        self.assertEqual(sheet["L2"].value, "acconto esistente")
        self.assertEqual(sheet["M2"].value, 1234.56)
        self.assertEqual(filled, 1)
        self.assertEqual(missing, 0)
        workbook.close()

    def test_existing_value_check_ignores_column_l(self):
        only_l = self._workbook_bytes(column_m=None)
        with_m = self._workbook_bytes(column_m="netto esistente")

        self.assertFalse(
            payment_file_has_existing_values(
                only_l, "pagamenti.xlsx", "Pagamenti", {"B001"}
            )
        )
        self.assertTrue(
            payment_file_has_existing_values(
                with_m, "pagamenti.xlsx", "Pagamenti", {"B001"}
            )
        )
