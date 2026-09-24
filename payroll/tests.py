"""Test cases for payroll."""

from django.test import TestCase

from employee.models import Employee
from payroll.views.component_views import _sync_employee_payroll_identity


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
