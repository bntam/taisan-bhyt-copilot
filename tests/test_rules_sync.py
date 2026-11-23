import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from data_engine.db import get_connection, init_schema
from data_engine.xuat_toan_rules_sync import sync_xuat_toan_rules, OFFICIAL_XUAT_TOAN_RULES

class TestRulesSync(unittest.TestCase):
    def test_sync_rules(self):
        conn = get_connection()
        init_schema(conn)
        res = sync_xuat_toan_rules(conn)
        self.assertEqual(res["status"], "SUCCESS")
        self.assertGreaterEqual(res["synced_count"], 15)
        
        c = conn.cursor()
        c.execute("SELECT count(*) FROM xuat_toan_rules")
        cnt = c.fetchone()[0]
        self.assertGreaterEqual(cnt, len(OFFICIAL_XUAT_TOAN_RULES))
        
        # Verify RULE_LIPID_TEST_MISSING exists and is HIGH severity
        c.execute("SELECT severity, remedy_suggestion FROM xuat_toan_rules WHERE rule_code = 'RULE_LIPID_TEST_MISSING'")
        row = c.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["severity"], "HIGH")
        print(f"Xuat Toan Rules sync verified: {cnt} rules in DB.")

if __name__ == "__main__":
    unittest.main()
