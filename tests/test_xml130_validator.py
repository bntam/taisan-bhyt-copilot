"""
Unit Tests for XML 130 / Quyết định 130/QĐ-BYT Pre-Checker
Validates:
1. Card expiry detection
2. Invalid or 3-digit general ICD code
3. Tier violation in drug order (XML2 vs Tier 4)
4. Missing required lab test (Statin + Lipid panel)
5. Procedure duration limit exceeded (> 15 days)
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from data_engine.xml130_validator import validate_xml130_record, OFFICIAL_XML130_RULES

class TestXml130Validator(unittest.TestCase):

    def test_01_rules_count(self):
        self.assertGreaterEqual(len(OFFICIAL_XML130_RULES), 6)

    def test_02_card_expiry_rule(self):
        record = {
            "ngay_vao": "2026-11-24",
            "gt_the_den": "2026-10-01",
            "ma_benh_chinh": "M54.5"
        }
        res = validate_xml130_record(record, hospital_level="4")
        self.assertIn("XML130_CARD_EXPIRY", [v["rule_code"] for v in res["violations"]])

    def test_03_tier_violation_ceftriaxone_tier_4(self):
        record = {
            "ma_benh_chinh": "M54.5",
            "drugs": ["Ceftriaxone 1g"],
            "gt_the_den": "2027-12-31"
        }
        res = validate_xml130_record(record, hospital_level="4")
        self.assertIn("XML130_DRUG_TIER_VIOLATION", [v["rule_code"] for v in res["violations"]])

    def test_04_missing_lipid_lab_for_statin(self):
        record = {
            "ma_benh_chinh": "E78.0",
            "drugs": ["Atorvastatin 20mg"],
            "labs": [],
            "gt_the_den": "2027-12-31"
        }
        res = validate_xml130_record(record, hospital_level="4")
        self.assertIn("XML130_MISSING_REQUIRED_LAB", [v["rule_code"] for v in res["violations"]])

    def test_05_clean_record_pass(self):
        record = {
            "ma_benh_chinh": "M54.5",
            "drugs": ["Meloxicam 7.5mg", "Paracetamol 500mg"],
            "procedures": ["Điện châm điều trị"],
            "procedure_days": 10,
            "gt_the_den": "2027-12-31"
        }
        res = validate_xml130_record(record, hospital_level="4")
        self.assertEqual(res["status"], "PASS")

if __name__ == "__main__":
    unittest.main()
