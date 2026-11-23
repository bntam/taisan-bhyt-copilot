"""
Automated Catalog Sync & Watchdog
Checks remote checksums, verifies update deltas, and updates the local SQLite catalog.
Can be executed as a daily/weekly cron job or triggered on-demand via MCP / REST API.
"""

import os
import sys
import json
import logging
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from data_engine.sync_catalog import sync_catalog, DB_PATH, METADATA_PATH

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def check_and_update(force=False):
    logging.info("Initiating BHYT Catalog Auto-Update Check...")
    
    if not os.path.exists(METADATA_PATH):
        logging.info("No prior sync metadata found. Performing initial full sync...")
        sync_catalog(force=True)
        return {"updated": True, "reason": "initial_sync"}
        
    try:
        with open(METADATA_PATH, "r", encoding="utf-8") as f:
            meta = json.load(f)
    except Exception as e:
        logging.warning(f"Error reading metadata: {e}. Forcing sync...")
        sync_catalog(force=True)
        return {"updated": True, "reason": "metadata_corrupt"}

    last_sync = meta.get("last_sync", "")
    logging.info(f"Current catalog sync timestamp: {last_sync} (ICD codes: {meta.get('icd_count')})")
    
    # Run sync to ensure latest catalog updates
    sync_catalog(force=force)
    logging.info("Auto-update check completed successfully.")
    return {"updated": True, "timestamp": datetime.now().isoformat()}

if __name__ == "__main__":
    force_flag = "--force" in sys.argv
    res = check_and_update(force=force_flag)
    print(json.dumps(res, indent=2))
