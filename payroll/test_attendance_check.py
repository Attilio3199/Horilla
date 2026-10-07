"""Regression tests for the practical attendance equivalences."""

import unittest

from payroll.services.attendance_check import reconcile_hours
from payroll.services.attendance_report import daily_summaries


class AttendanceEquivalenceTests(unittest.TestCase):
    leave = {v: {"FERIE", "ROL"} for v in (302, 335, 303, 336, 337, 304)}
    worked = {300: {"LAVORATO", "SMART WORKING", "CORSO AI DIPENDENTI"}}

    def test_leave_equivalence_in_both_directions(self):
        for kind in ("FERIE", "ROL"):
            for voice in self.leave:
                with self.subTest(kind=kind, voice=voice):
                    self.assertEqual(reconcile_hours({kind: 8}, {voice: 8}, self.leave), [])

    def test_leave_split_between_multiple_voices(self):
        self.assertEqual(reconcile_hours({"FERIE": 8}, {302: 4, 303: 4}, self.leave), [])

    def test_work_smart_work_and_course_share_one_voice(self):
        self.assertEqual(reconcile_hours(
            {"LAVORATO": 2, "SMART WORKING": 4, "CORSO AI DIPENDENTI": 2},
            {300: 8}, self.worked), [])

    def test_missing_hours(self):
        diff = reconcile_hours({"SMART WORKING": 8}, {300: 6}, self.worked)[0]
        self.assertEqual(diff["missing"], 2)
        self.assertEqual(diff["extra"], 0)

    def test_excess_leave_hours(self):
        diff = reconcile_hours({"FERIE": 8}, {302: 8, 303: 8}, self.leave)[0]
        self.assertEqual(diff["extra"], 8)

    def test_payslip_hours_cannot_cover_two_app_types_twice(self):
        diff = reconcile_hours({"FERIE": 8, "ROL": 8}, {302: 8}, self.leave)[0]
        self.assertEqual(diff["missing"], 8)

    def test_wrong_categories_do_not_cancel_each_other(self):
        diff = reconcile_hours({"FERIE": 8}, {300: 8}, self.leave | self.worked)
        self.assertEqual(len(diff), 2)

    def test_overlapping_rules_require_real_allocation(self):
        allowed = {1: {"A", "B"}, 2: {"B"}}
        self.assertEqual(reconcile_hours({"A": 4, "B": 4}, {1: 4, 2: 4}, allowed), [])
        diff = reconcile_hours({"A": 8}, {1: 4, 2: 4}, allowed)[0]
        self.assertEqual(diff["missing"], 4)
        self.assertEqual(diff["extra"], 4)

    def test_zero_and_rounding_tolerance(self):
        self.assertEqual(reconcile_hours({}, {}, self.leave), [])
        self.assertEqual(reconcile_hours({"FERIE": 8}, {302: 7.95}, self.leave), [])
        self.assertTrue(reconcile_hours({"FERIE": 8}, {302: 7.94}, self.leave))

    def test_negative_hours_are_reported(self):
        self.assertTrue(reconcile_hours({"FERIE": 8}, {302: 9, 303: -1}, self.leave))


class AttendanceReportTests(unittest.TestCase):
    def test_same_day_is_combined_and_causales_are_named(self):
        rows = [
            {"giorno": 21, "dettaglio_app": [], "dettaglio_cedolino": [
                {"causale": "ASSENZA NON RETRIBUITA (ASSENZE)", "ore": 4}]},
            {"giorno": 21, "dettaglio_app": [{"causale": "FERIE", "ore": 6}],
             "dettaglio_cedolino": [{"causale": "ROL (FEST.SOPPR)", "ore": 2}]},
        ]
        result = daily_summaries(rows)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["app"], "FERIE: 6 h")
        self.assertIn("ROL (FEST.SOPPR): 2 h", result[0]["cedolino"])
        self.assertIn("Totale delle causali confrontate uguale (6 h)", result[0]["esito"])
        self.assertIn("causali non equivalenti", result[0]["esito"])

    def test_real_hour_difference_is_explicit(self):
        result = daily_summaries([{
            "giorno": 22, "dettaglio_app": [{"causale": "FERIE", "ore": 6}],
            "dettaglio_cedolino": [{"causale": "ROL", "ore": 4}],
        }])[0]
        self.assertIn("Differenza: -2 h", result["esito"])


if __name__ == "__main__":
    unittest.main()
