import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from data_engine.updater import check_for_updates, execute_full_sync, get_sync_metadata

class TestUpdater(unittest.TestCase):
    def test_updater_flow(self):
        # 1. Test check for updates
        up_check = check_for_updates()
        self.assertIn("update_needed", up_check)
        self.assertIn("reason", up_check)
        print(f"Update check: needed={up_check['update_needed']}, reason={up_check['reason']}")
        
        # 2. Test full sync
        res = execute_full_sync(create_backup=False)
        self.assertEqual(res["status"], "SUCCESS")
        self.assertGreater(res["counts"]["icd10"], 15000)
        self.assertGreater(res["counts"]["thuoc_bhyt"], 15)
        self.assertGreater(res["counts"]["thu_thuat_bhyt"], 9)
        self.assertGreater(res["counts"]["thuoc_yhct"], 9)
        self.assertGreater(res["counts"]["xuat_toan_rules"], 15)
        
        # 3. Test metadata
        meta = get_sync_metadata()
        self.assertIsNotNone(meta["last_sync"])
        self.assertGreater(meta["counts"]["icd10"], 15000)
        print(f"Full sync verified: {meta['counts']}")

if __name__ == "__main__":
    unittest.main()
