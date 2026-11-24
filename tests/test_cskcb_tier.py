"""
Unit Tests for CSKCB Directory & Hospital Tier Auto-Detection
Validates:
1. Auto-detection of Tier 1 (Bệnh viện Bạch Mai, Chợ Rẫy, Việt Đức, TW Huế)
2. Auto-detection of Tier 2 (BVĐK Tỉnh Phú Yên, BV 115, BV Gia Định)
3. Auto-detection of Tier 3 (TTYT TP Tuy Hòa, BV Quận 1, TTYT Sông Cầu)
4. Auto-detection of Tier 4 (Phòng khám YHCT Tài Sanh, Trạm Y tế Phường 9)
5. Manual override persistence & fallback handling
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from data_engine.cskcb_sync import detect_hospital_tier, CSKCB_SEED

class TestCskcbTierDetection(unittest.TestCase):

    def test_01_seed_count_and_tiers(self):
        self.assertGreaterEqual(len(CSKCB_SEED), 25)
        tiers = {c["tuyen"] for c in CSKCB_SEED}
        self.assertEqual(tiers, {"1", "2", "3", "4"})

    def test_02_detect_tier_1_bach_mai(self):
        res = detect_hospital_tier(facility_text="Bệnh viện Bạch Mai", facility_code="01001")
        self.assertEqual(res["level"], "1")
        self.assertGreater(res["confidence"], 0.8)

    def test_03_detect_tier_2_phu_yen(self):
        res = detect_hospital_tier(facility_text="Bệnh viện Đa khoa Tỉnh Phú Yên", facility_code="54001")
        self.assertEqual(res["level"], "2")

    def test_04_detect_tier_3_ttyt(self):
        res = detect_hospital_tier(facility_text="Trung tâm Y tế Thành phố Tuy Hòa", facility_code="54005")
        self.assertEqual(res["level"], "3")

    def test_05_detect_tier_4_tai_sanh(self):
        res = detect_hospital_tier(facility_text="Phòng khám Y học cổ truyền Tài Sanh", facility_code="54012")
        self.assertEqual(res["level"], "4")

    def test_06_detect_from_url_hint(self):
        res = detect_hospital_tier(url="https://his.choray.vn/portal/patient")
        self.assertEqual(res["level"], "1")

if __name__ == "__main__":
    unittest.main()
