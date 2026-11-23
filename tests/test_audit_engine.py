"""
Unit and Integration Test Suite for TaiSanh BHYT Clinical Copilot
Validates:
1. ICD-10 Search & Regulatory Subcode Enforcement
2. Drug Hospital Level Restrictions (Tuyến 4 PKDK / Trạm Y tế)
3. Required Clinical Lab Test Verification (Statin & Lipid Panel)
4. Traditional Chinese/Vietnamese Medicine (YHCT) Procedure Limits (<= 15 days)
5. Herb-Drug Bleeding & Interaction Safety Guard
6. Clinical Note Justification Generation
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from mcp_server.server import (
    search_icd10,
    validate_prescription,
    suggest_clinical_note,
    check_herb_drug_interaction
)

class TestBHYTAuditEngine(unittest.TestCase):

    def test_01_search_icd10_vietnamese(self):
        results = search_icd10("thoái hóa khớp", limit=5)
        self.assertGreater(len(results), 0)
        self.assertTrue(any("thoái hóa" in r["name_vn"].lower() for r in results))

    def test_02_detect_must_use_subcode(self):
        # M16 has must_use_subcode = 1
        val = validate_prescription(icd_code="M16", drugs=["Paracetamol 500mg"], hospital_level="4")
        self.assertEqual(val["status"], "FAIL_RISK")
        subcode_alert = any(a["rule"] == "MUST_USE_SUBCODE" for a in val["alerts"])
        self.assertTrue(subcode_alert, "Should detect 3-digit ICD code that requires 4-digit subcode")

    def test_03_detect_drug_hospital_level_exceeded(self):
        # Ceftriaxone is only allowed for Level 1, 2, 3. Level 4 clinic must be flagged!
        val = validate_prescription(icd_code="J18.0", drugs=["Ceftriaxone 1g"], hospital_level="4")
        self.assertEqual(val["status"], "FAIL_RISK")
        level_alert = any(a["rule"] == "HOSPITAL_LEVEL_EXCEEDED" for a in val["alerts"])
        self.assertTrue(level_alert, "Ceftriaxone at Level 4 clinic must trigger HOSPITAL_LEVEL_EXCEEDED")

    def test_04_detect_missing_required_lab(self):
        # Atorvastatin without lipid panel
        val = validate_prescription(icd_code="E78.0", drugs=["Atorvastatin 20mg"], hospital_level="4", lab_tests=[])
        self.assertEqual(val["status"], "FAIL_RISK")
        lab_alert = any(a["rule"] == "MISSING_REQUIRED_LAB" for a in val["alerts"])
        self.assertTrue(lab_alert, "Atorvastatin without lipid lab must trigger MISSING_REQUIRED_LAB")

    def test_05_detect_procedure_duration_limit(self):
        # Điện châm > 15 days in one outpatient episode
        val = validate_prescription(
            icd_code="M54.5", 
            drugs=["Paracetamol 500mg"], 
            hospital_level="4",
            procedures=["Điện châm điều trị"],
            procedure_days=18
        )
        proc_alert = any(a["rule"] == "PROCEDURE_DAYS_EXCEEDED" for a in val["alerts"])
        self.assertTrue(proc_alert, "Điện châm > 15 days must trigger PROCEDURE_DAYS_EXCEEDED")

    def test_06_detect_herb_drug_interaction(self):
        # Đan sâm or Đương quy with Aspirin
        warnings = check_herb_drug_interaction(
            tcm_herbs=["Đan sâm", "Bạch thược"],
            western_drugs=["Aspirin 81mg", "Amlodipine 5mg"]
        )
        self.assertGreater(len(warnings), 0)
        self.assertTrue(any("xuất huyết" in w["detail"].lower() for w in warnings))

    def test_07_suggest_clinical_justification(self):
        note = suggest_clinical_note(icd_code="M54.5", procedures=["Điện châm điều trị", "Xoa bóp bấm huyệt"])
        self.assertIn("M54.5", note["icd_code"])
        self.assertIn("Khám thực thể", note["suggested_note"])
        self.assertIn("Chẩn đoán YHCT", note["suggested_note"])

    def test_08_pass_clean_prescription(self):
        # Clean outpatient prescription with valid subcode, permitted oral drugs, and lab tests
        val = validate_prescription(
            icd_code="E11.9", # Đái tháo đường type 2 không biến chứng
            drugs=["Metformin 500mg"],
            hospital_level="4",
            procedures=[],
            lab_tests=["Glucose máu mao mạch", "HbA1c"],
            procedure_days=1
        )
        self.assertEqual(val["high_risk_count"], 0)
        self.assertEqual(val["status"], "PASS")

if __name__ == "__main__":
    unittest.main()
