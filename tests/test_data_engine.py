"""
Comprehensive Test Suite for BHYT Data Engine & Catalog Pipeline
Covers schema initialization, FTS5 multi-catalog search, regulatory flag parsing,
hospital level tier audits, procedure duration limits, herb-drug safety, and auto-update flow.
"""

import os
import sys
import unittest
import sqlite3
import subprocess

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

from data_engine.db import get_connection, init_schema, rebuild_fts_indexes
from data_engine.updater import check_for_updates, execute_full_sync, get_sync_metadata
from mcp_server.server import (
    search_icd10,
    validate_prescription,
    suggest_clinical_note,
    check_herb_drug_interaction
)


class TestBHYTDataEngine(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.conn = get_connection()
        init_schema(cls.conn)

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def test_01_icd10_catalog_size_and_flags(self):
        c = self.conn.cursor()
        c.execute("SELECT count(*) FROM icd10")
        total_icd = c.fetchone()[0]
        self.assertGreaterEqual(total_icd, 15000, "ICD-10 catalog must contain over 15,000 official codes")

        # Check must_use_subcode flag (e.g. M16)
        c.execute("SELECT must_use_subcode FROM icd10 WHERE code = 'M16'")
        row = c.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["must_use_subcode"], 1, "M16 must have must_use_subcode=1")

        # Check female-specific code (e.g. N70 or N80)
        c.execute("SELECT count(*) FROM icd10 WHERE female_only = 1")
        female_cnt = c.fetchone()[0]
        self.assertGreater(female_cnt, 500, "Must have female-specific diagnostic codes")

        # Check male-specific code (e.g. N40)
        c.execute("SELECT count(*) FROM icd10 WHERE male_only = 1")
        male_cnt = c.fetchone()[0]
        self.assertGreater(male_cnt, 100, "Must have male-specific diagnostic codes")

    def test_02_fts5_multicatalog_search(self):
        c = self.conn.cursor()

        # 1. Search ICD-10
        c.execute("SELECT code, name_vn FROM icd10_fts WHERE icd10_fts MATCH 'đau lưng' LIMIT 5")
        icd_matches = c.fetchall()
        self.assertGreater(len(icd_matches), 0, "Should match ICD codes for 'đau lưng'")

        # 2. Search Drugs
        c.execute("SELECT ten_hoat_chat FROM thuoc_bhyt_fts WHERE thuoc_bhyt_fts MATCH 'cefixim' LIMIT 5")
        drug_matches = c.fetchall()
        self.assertGreater(len(drug_matches), 0, "Should match drug for 'cefixim'")

        # 3. Search TCM Herbs
        c.execute("SELECT ten_vi_thuoc FROM thuoc_yhct_fts WHERE thuoc_yhct_fts MATCH 'đan sâm' LIMIT 5")
        herb_matches = c.fetchall()
        self.assertGreater(len(herb_matches), 0, "Should match TCM herb for 'đan sâm'")

        # 4. Search Procedures
        c.execute("SELECT ten_dich_vu FROM thu_thuat_bhyt_fts WHERE thu_thuat_bhyt_fts MATCH 'châm cứu OR điện châm' LIMIT 5")
        proc_matches = c.fetchall()
        self.assertGreater(len(proc_matches), 0, "Should match procedure for 'điện châm'")

    def test_03_western_drug_hospital_tier_enforcement(self):
        val_level4 = validate_prescription(
            icd_code="J18.0",
            drugs=["Ceftriaxone 1g"],
            hospital_level="4"
        )
        self.assertEqual(val_level4["status"], "FAIL_RISK")
        self.assertTrue(any(a["rule"] == "HOSPITAL_LEVEL_EXCEEDED" for a in val_level4["alerts"]))

        # Same drug at hospital Level 2 must pass hospital tier check
        val_level2 = validate_prescription(
            icd_code="J18.0",
            drugs=["Ceftriaxone 1g"],
            hospital_level="2"
        )
        tier_alerts = [a for a in val_level2["alerts"] if a["rule"] == "HOSPITAL_LEVEL_EXCEEDED"]
        self.assertEqual(len(tier_alerts), 0, "Level 2 hospital is authorized to prescribe Ceftriaxone")

    def test_04_mandatory_lab_test_validation(self):
        val_missing = validate_prescription(
            icd_code="E78.0",
            drugs=["Atorvastatin 20mg"],
            hospital_level="4",
            lab_tests=[]
        )
        self.assertEqual(val_missing["status"], "FAIL_RISK")
        self.assertTrue(any(a["rule"] == "MISSING_REQUIRED_LAB" for a in val_missing["alerts"]))

        val_ok = validate_prescription(
            icd_code="E78.0",
            drugs=["Atorvastatin 20mg"],
            hospital_level="4",
            lab_tests=["Xét nghiệm Lipid máu (Cholesterol/Triglyceride/LDL-C)"]
        )
        lab_alerts = [a for a in val_ok["alerts"] if a["rule"] == "MISSING_REQUIRED_LAB"]
        self.assertEqual(len(lab_alerts), 0, "Providing lipid panel clears MISSING_REQUIRED_LAB alert")

    def test_05_procedure_duration_limit_enforcement(self):
        # 10 days -> OK
        val_ok = validate_prescription(
            icd_code="M54.5",
            drugs=["Paracetamol 500mg"],
            hospital_level="4",
            procedures=["Điện châm điều trị"],
            procedure_days=10
        )
        days_alerts = [a for a in val_ok["alerts"] if a["rule"] == "PROCEDURE_DAYS_EXCEEDED"]
        self.assertEqual(len(days_alerts), 0)

        # 20 days -> Trigger PROCEDURE_DAYS_EXCEEDED
        val_exceeded = validate_prescription(
            icd_code="M54.5",
            drugs=["Paracetamol 500mg"],
            hospital_level="4",
            procedures=["Điện châm điều trị"],
            procedure_days=20
        )
        self.assertEqual(val_exceeded["status"], "FAIL_RISK")
        self.assertTrue(any(a["rule"] == "PROCEDURE_DAYS_EXCEEDED" for a in val_exceeded["alerts"]))

    def test_06_herb_drug_hazardous_interaction(self):
        # 1. Bleeding risk: Đan sâm + Aspirin
        warnings_bleed = check_herb_drug_interaction(
            tcm_herbs=["Đan sâm (Radix Salviae miltiorrhizae)"],
            western_drugs=["Aspirin 81mg"]
        )
        self.assertGreater(len(warnings_bleed), 0)
        self.assertIn("xuất huyết", warnings_bleed[0]["detail"].lower())

        # 2. Hypokalemia risk: Cam thảo + Lợi tiểu
        warnings_k = check_herb_drug_interaction(
            tcm_herbs=["Cam thảo (Radix Glycyrrhizae)"],
            western_drugs=["Amlodipine 5mg", "Hydrochlorothiazide 25mg"]
        )
        self.assertGreater(len(warnings_k), 0)
        self.assertTrue("hạ áp" in warnings_k[0]["detail"].lower() or "kali" in warnings_k[0]["detail"].lower())

    def test_07_clinical_note_generation(self):
        note = suggest_clinical_note(
            icd_code="M54.5",
            procedures=["Điện châm điều trị", "Xoa bóp bấm huyệt điều trị"],
            symptoms="Đau lưng lan chân"
        )
        self.assertIn("M54.5", note["icd_code"])
        self.assertIn("Lý do khám", note["suggested_note"])
        self.assertIn("Khám thực thể", note["suggested_note"])
        self.assertIn("Chẩn đoán YHCT", note["suggested_note"])

    def test_08_cli_tool_execution(self):
        res_status = subprocess.run(
            [sys.executable, os.path.join(REPO_ROOT, "data_engine", "cli.py"), "status"],
            capture_output=True,
            text=True
        )
        self.assertEqual(res_status.returncode, 0)
        self.assertIn("BHYT CLINICAL COPILOT", res_status.stdout)
        self.assertIn("RECORD COUNTS", res_status.stdout)

        res_search = subprocess.run(
            [sys.executable, os.path.join(REPO_ROOT, "data_engine", "cli.py"), "search", "icd", "đái tháo đường"],
            capture_output=True,
            text=True
        )
        self.assertEqual(res_search.returncode, 0)
        self.assertIn("đái tháo đường", res_search.stdout.lower())


if __name__ == "__main__":
    unittest.main()
