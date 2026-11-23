import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from data_engine.db import get_connection, init_schema
from data_engine.thuoc_tt20_sync import sync_thuoc_bhyt, OFFICIAL_TT20_DRUGS

class TestThuocSync(unittest.TestCase):
    def test_sync_thuoc_tt20(self):
        conn = get_connection()
        init_schema(conn)
        res = sync_thuoc_bhyt(conn)
        self.assertEqual(res["status"], "SUCCESS")
        self.assertGreaterEqual(res["synced_count"], 15)
        
        c = conn.cursor()
        c.execute("SELECT count(*) FROM thuoc_bhyt")
        cnt = c.fetchone()[0]
        self.assertGreaterEqual(cnt, len(OFFICIAL_TT20_DRUGS))
        
        # Verify Ceftriaxone hospital level restriction is 1,2,3
        c.execute("SELECT hang_bv_duoc_ke FROM thuoc_bhyt WHERE ten_hoat_chat LIKE '%Ceftriaxone%'")
        row = c.fetchone()
        self.assertIsNotNone(row)
        self.assertNotIn("4", row["hang_bv_duoc_ke"].split(","))
        print(f"Thuoc TT20 sync verified: {cnt} drugs in DB, tier restrictions intact.")

if __name__ == "__main__":
    unittest.main()
