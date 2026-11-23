import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from data_engine.db import get_connection, init_schema, rebuild_fts_indexes

class TestDBInit(unittest.TestCase):
    def test_schema_and_fts(self):
        conn = get_connection()
        init_schema(conn)
        rebuild_fts_indexes(conn)
        c = conn.cursor()
        
        # Test ICD-10 FTS search
        c.execute("SELECT code, name_vn FROM icd10_fts WHERE icd10_fts MATCH 'khớp' LIMIT 5")
        rows = c.fetchall()
        self.assertGreater(len(rows), 0, "Should find ICD-10 matches for 'khớp'")
        
        # Test Drug FTS search
        c.execute("SELECT ten_hoat_chat FROM thuoc_bhyt_fts WHERE thuoc_bhyt_fts MATCH 'paracetamol' LIMIT 5")
        drug_rows = c.fetchall()
        self.assertGreater(len(drug_rows), 0, "Should find drug matches for 'paracetamol'")
        
        print(f"Verified schema & FTS5 search: {len(rows)} ICD rows matched 'khớp', {len(drug_rows)} drug rows matched 'paracetamol'.")

if __name__ == "__main__":
    unittest.main()
