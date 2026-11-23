"""
Unit and Integration Test Suite for Clinical AI Q&A Copilot (Chatbox Engine)
Validates:
1. Herb-Drug interaction inquiry: Cam thảo & Tăng huyết áp
2. Herb-Drug bleeding risk: Đan sâm & Aspirin / Warfarin
3. Clinic Level 4 (Tuyến 4) prescribing restrictions for ICD M54.5
4. Outpatient procedure duration limits: Điện châm / Xoa bóp <= 15 days
5. Required lab test compliance: Atorvastatin & Lipid panel
6. FastAPI /api/chat endpoint response structure
"""

import sys
import os
import unittest
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from mcp_server.server import ask_clinical_copilot

class TestClinicalChatbox(unittest.TestCase):

    def test_01_ask_cam_thao_hypertension(self):
        res = ask_clinical_copilot("Bệnh nhân tăng huyết áp có dùng được Cam thảo không?")
        self.assertIn("Cam Thảo", res["answer"])
        self.assertIn("Glycyrrhizin", res["answer"])
        self.assertIn("hạ Kali", res["answer"])
        self.assertGreater(len(res["references"]), 0)

    def test_02_ask_dan_sam_aspirin_bleeding(self):
        res = ask_clinical_copilot("Đan sâm có dùng chung được với Aspirin hoặc thuốc chống đông không?")
        self.assertIn("xuất huyết", res["answer"].lower())
        self.assertIn("tiểu cầu", res["answer"].lower())
        self.assertGreater(len(res["references"]), 0)

    def test_03_ask_level_4_prescribing_m54(self):
        res = ask_clinical_copilot("Mã M54.5 ở phòng khám tư (tuyến 4) được kê thuốc giảm đau nào?")
        self.assertIn("Paracetamol", res["answer"])
        self.assertIn("Ceftriaxone", res["answer"])
        self.assertIn("Xuất toán", res["answer"])
        self.assertTrue(len(res["suggested_snippet"]) > 0)

    def test_04_ask_procedure_duration_limit(self):
        res = ask_clinical_copilot("Điện châm và xoa bóp bấm huyệt tối đa bao nhiêu ngày trong 1 đợt điều trị?")
        self.assertIn("15 ngày", res["answer"])
        self.assertIn("nghỉ", res["answer"])

    def test_05_ask_statin_lab_requirement(self):
        res = ask_clinical_copilot("Kê thuốc hạ mỡ máu Atorvastatin cần xét nghiệm gì?")
        self.assertIn("lipid", res["answer"].lower())
        self.assertIn("Cholesterol", res["answer"])
        self.assertIn("E78", res["answer"])

    def test_06_ask_fallback_guidance(self):
        res = ask_clinical_copilot("Quy định chung về chuyển tuyến BHYT")
        self.assertIn("query", res)
        self.assertIn("answer", res)
        self.assertGreater(len(res["related_queries"]), 0)

    def test_07_ask_yhct_mapping_4443(self):
        res = ask_clinical_copilot("Chứng Tọa cốt phong trong YHCT tương đương mã ICD nào?")
        self.assertIn("Tọa cốt phong", res["answer"])
        self.assertIn("M54.5", res["answer"])
        self.assertIn("4443", res["references"][0])

    def test_08_ask_context_evaluation(self):
        ctx = {
            "icd_code": "M54.5",
            "drugs": ["Ceftriaxone 1g", "Paracetamol 500mg"],
            "procedures": ["Điện châm điều trị"],
            "procedure_days": 18
        }
        res = ask_clinical_copilot("Đơn này có hợp lệ không?", context=ctx)
        self.assertIn("M54.5", res["answer"])
        self.assertIn("CẢNH BÁO", res["answer"])
        self.assertIn("xuất toán", res["answer"].lower())

    def test_09_fastapi_chat_endpoint(self):
        from fastapi.testclient import TestClient
        from mcp_server.api import app
        client = TestClient(app)
        response = client.post("/api/chat", json={
            "message": "Cam thảo có dùng chung với thuốc hạ huyết áp được không?",
            "context": {"hospital_level": "4"}
        })
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("answer", data)
        self.assertIn("Cam Thảo", data["answer"])
        self.assertIn("references", data)
        self.assertGreater(len(data["references"]), 0)

if __name__ == "__main__":
    unittest.main()
