"""Tests for the I/O Manager's pure helpers (validation and record
conversion). Screens and prompts are covered by the end-to-end check in
the README, since they need a real terminal."""

import contextlib
import io
import unittest
from unittest import mock

import io_manager as io_mgr


class KeyVerifierTests(unittest.TestCase):
    def check(self, text):
        with contextlib.redirect_stdout(io.StringIO()):
            return io_mgr.key_verifier(text)

    def test_valid_numbers(self):
        self.assertEqual(self.check("7"), 7)
        self.assertEqual(self.check(" 10 "), 10)

    def test_rejects_everything_else(self):
        for text in ("", "  ", "a", "-1", "1.5", "123", "１", None, 5):
            self.assertIsNone(self.check(text), repr(text))


class UsernameTests(unittest.TestCase):
    def test_valid(self):
        for name in ("abc", "tim_01", "a" * 20):
            self.assertTrue(io_mgr.is_valid_username(name), name)

    def test_invalid(self):
        for name in ("ab", "a" * 21, "has space", "bad-name", "../x", "naïve", ""):
            self.assertFalse(io_mgr.is_valid_username(name), name)


class FiniteFloatTests(unittest.TestCase):
    def test_numbers(self):
        self.assertEqual(io_mgr.finite_float("12.5"), 12.5)

    def test_nan_and_infinity_are_refused(self):
        for text in ("nan", "inf", "-inf", "x"):
            with self.assertRaises(ValueError):
                io_mgr.finite_float(text)


class RecordConversionTests(unittest.TestCase):
    NESTED = {
        "audit_id": 1,
        "company_profile": {
            "company_name": "Acme", "annual_revenue_sgd": 5.0, "group_employment_size": 3,
            "local_shareholding_pct": 80.0, "proposal_type": "ESG Reporting / Advisory",
            "reporting_advisory_fee_sgd": 1000.0,
        },
        "proposal": {"raw_narrative": "Our plan"},
    }

    def test_nested_record_becomes_the_display_layout(self):
        flat = io_mgr.flat_record(self.NESTED)
        self.assertEqual(flat["Company Name"], "Acme")
        self.assertEqual(flat["Proposal Narrative"], "Our plan")
        self.assertEqual(flat["Reporting Advisory Fee"], 1000.0)

    def test_flat_record_is_left_alone(self):
        record = {"Company Name": "Beta"}
        self.assertIs(io_mgr.flat_record(record), record)

    def test_garbage_gives_an_empty_record(self):
        for value in (None, 5, "x", []):
            self.assertEqual(io_mgr.flat_record(value), {})

    def test_conversion_to_the_logic_profile(self):
        profile = io_mgr.convert_record_to_profile({
            "Company Name": "Beta", "Company Total Revenue": 10.0, "Total Employees": 4,
            "Local Equity": 55.0, "Proposal Type": "Equipment / Energy Upgrade",
            "Baseline Energy Expenditure": 99.0,
        })
        self.assertEqual(profile["annual_revenue_sgd"], 10.0)
        self.assertEqual(profile["baseline_annual_energy_expenditure_sgd"], 99.0)
        self.assertEqual(profile["estimated_retrofit_cost_sgd"], 0.0)

    def test_missing_fields_do_not_crash(self):
        profile = io_mgr.convert_record_to_profile({})
        self.assertEqual(profile["annual_revenue_sgd"], 0.0)

    def test_displaying_damaged_records_does_not_crash(self):
        # return_button waits for a real key press, so it is replaced here.
        with contextlib.redirect_stdout(io.StringIO()), \
                mock.patch.object(io_mgr.gui, "return_button"):
            io_mgr.display_applied_grants([{}, {"Company Name": None}, 5], 4)


if __name__ == "__main__":
    unittest.main()
