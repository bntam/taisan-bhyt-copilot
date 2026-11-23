import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from data_engine.db import get_connection, init_schema
from data_engine.yhct_tt27_sync import sync_thuoc_yhct, sync_yhct_icd10_mapping, OFFICIAL_TT27_HERBS, OFFICIAL_YHCT_MAPPINGS

class TestYHCTSync(unittest.TestCase):
    def test_sync_yhct_data(self):
        conn = get_connection()
        init_schema(conn)
        res_herbs = sync_thuoc_yhct(conn)
        res_maps = sync_yhct_icd10_mapping(conn)
        
        self.assertEqual(res_herbs["status"], "SUCCESS")
        self.assertEqual(res_maps["status"], "SUCCESS")
        
        c = conn.cursor()
        c.execute("SELECT count(*) FROM thuoc_yhct")
        cnt_h = c.fetchone()[0]
        self.assertGreaterEqual(cnt_h, len(OFFICIAL_TT27_HERBS))
        
        c.execute("SELECT count(*) FROM yhct_icd10_mapping")
        cnt_m = c.fetchone()[0]
        self.assertGreaterEqual(cnt_m, len(OFFICIAL_YHCT_MAPPINGS))
        
        # Verify Dan sam contraindication / western interaction exists
        c.execute("SELECT tuong_tac_tay_y FROM thuoc_yhct WHERE ten_vi_thuoc LIKE '%Đan sâm%'")
        row = c.fetchone()
        self.assertIn("Aspirin", row["tuong_tac_tay_y"])
        print(f"YHCT TT27 sync verified: {cnt_h} herbs and {cnt_m} mappings in DB.")

if __name__ == "__main__":
    unittest.main()
