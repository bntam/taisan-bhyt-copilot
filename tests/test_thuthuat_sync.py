import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from data_engine.db import get_connection, init_schema
from data_engine.thu_thuat_tt13_sync import sync_thu_thuat_bhyt, OFFICIAL_TT13_PROCEDURES

class TestThuThuatSync(unittest.TestCase):
    def test_sync_thu_thuat(self):
        conn = get_connection()
        init_schema(conn)
        res = sync_thu_thuat_bhyt(conn)
        self.assertEqual(res["status"], "SUCCESS")
        self.assertGreaterEqual(res["synced_count"], 10)
        
        c = conn.cursor()
        c.execute("SELECT count(*) FROM thu_thuat_bhyt")
        cnt = c.fetchone()[0]
        self.assertGreaterEqual(cnt, len(OFFICIAL_TT13_PROCEDURES))
        
        # Verify Dien cham max days is 15
        c.execute("SELECT so_ngay_toi_da FROM thu_thuat_bhyt WHERE ma_dich_vu = 'TT.YHCT.01'")
        row = c.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["so_ngay_toi_da"], 15)
        print(f"Thu Thuat TT13 sync verified: {cnt} procedures in DB.")

if __name__ == "__main__":
    unittest.main()
