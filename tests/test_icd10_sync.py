import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from data_engine.db import get_connection, init_schema
from data_engine.icd10_sync import parse_and_sync_icd10

class TestICD10Sync(unittest.TestCase):
    def test_sync_icd10(self):
        conn = get_connection()
        init_schema(conn)
        stats = parse_and_sync_icd10(conn)
        self.assertEqual(stats["status"], "SUCCESS")
        self.assertGreaterEqual(stats["total_synced"], 15000)
        self.assertGreater(stats["must_use_subcode"], 2000)
        self.assertGreater(stats["not_allowed_primary"], 2000)
        
        c = conn.cursor()
        c.execute("SELECT count(*) FROM icd10")
        total = c.fetchone()[0]
        self.assertEqual(total, stats["total_synced"])
        print(f"ICD-10 sync verified: {total} records successfully in DB.")

if __name__ == "__main__":
    unittest.main()
