#!/usr/bin/env python3
import unittest
import subprocess
import sys
import json
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

class TestMCPStdio(unittest.TestCase):
    def run_mcp_session(self, requests):
        input_data = "\n".join(json.dumps(r) for r in requests) + "\n"
        proc = subprocess.run(
            [sys.executable, os.path.join(REPO_ROOT, "mcp_server", "mcp_stdio.py")],
            input=input_data,
            capture_output=True,
            text=True,
            cwd=REPO_ROOT
        )
        responses = []
        for line in proc.stdout.strip().split("\n"):
            if line.strip():
                responses.append(json.loads(line))
        return responses, proc.stderr

    def test_01_initialize_and_tools_list(self):
        reqs = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
        ]
        resps, stderr = self.run_mcp_session(reqs)
        self.assertEqual(len(resps), 2)
        
        # Verify initialize response
        init_res = resps[0]
        self.assertEqual(init_res["id"], 1)
        self.assertEqual(init_res["result"]["serverInfo"]["name"], "taisan-bhyt-copilot")
        
        # Verify tools/list
        tools_res = resps[1]
        self.assertEqual(tools_res["id"], 2)
        tool_names = [t["name"] for t in tools_res["result"]["tools"]]
        self.assertIn("validate_prescription", tool_names)
        self.assertIn("search_icd10", tool_names)
        self.assertIn("check_herb_drug_interaction", tool_names)
        self.assertIn("suggest_clinical_note", tool_names)
        self.assertIn("ask_clinical_copilot", tool_names)

    def test_02_tools_call_validate(self):
        reqs = [
            {
                "jsonrpc": "2.0",
                "id": 10,
                "method": "tools/call",
                "params": {
                    "name": "validate_prescription",
                    "arguments": {
                        "icd_code": "M54.5",
                        "drugs": ["Ceftriaxone 1g", "Paracetamol 500mg"],
                        "hospital_level": "4",
                        "procedures": ["Điện châm điều trị"],
                        "procedure_days": 18
                    }
                }
            }
        ]
        resps, stderr = self.run_mcp_session(reqs)
        self.assertEqual(len(resps), 1)
        call_res = resps[0]
        self.assertEqual(call_res["id"], 10)
        self.assertIn("result", call_res)
        text_content = call_res["result"]["content"][0]["text"]
        data = json.loads(text_content)
        self.assertIn(data["status"], ["FAIL_RISK", "REJECT"])
        self.assertGreater(data["high_risk_count"], 0)

    def test_03_tools_call_search_icd10(self):
        reqs = [
            {
                "jsonrpc": "2.0",
                "id": 20,
                "method": "tools/call",
                "params": {
                    "name": "search_icd10",
                    "arguments": {
                        "keyword": "thoát vị đĩa đệm",
                        "limit": 3
                    }
                }
            }
        ]
        resps, stderr = self.run_mcp_session(reqs)
        self.assertEqual(len(resps), 1)
        call_res = resps[0]
        self.assertEqual(call_res["id"], 20)
        text_content = call_res["result"]["content"][0]["text"]
        data = json.loads(text_content)
        self.assertGreater(len(data), 0)
        self.assertTrue(any("M51" in r["code"] for r in data))

if __name__ == "__main__":
    unittest.main()
