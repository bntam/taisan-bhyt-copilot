"""
Automated Catalog Sync & Watchdog for BHYT Clinical Copilot
Runs on schedule (e.g. daily/weekly cron) or can be invoked on-demand.
Checks remote datasets, updates SQLite catalog atomically, and maintains audit logs.
"""

import os
import sys
import json
import logging
from datetime import datetime
from typing import Dict, Any

# Setup paths
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BASE_DIR)

from data_engine.updater import check_for_updates, execute_full_sync, get_sync_metadata, DB_PATH, METADATA_PATH

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("bhyt.cron_updater")


def run_auto_update_job(force: bool = False, create_backup: bool = True) -> Dict[str, Any]:
    """Execute scheduled check and update if necessary."""
    logger.info("Running BHYT catalog watchdog check...")
    update_info = check_for_updates()

    if update_info["update_needed"] or force:
        logger.info(f"Update needed ({update_info['reason']}). Launching full sync...")
        sync_result = execute_full_sync(force_download=force, create_backup=create_backup)
        logger.info("Synchronization succeeded.")
        return {
            "action": "SYNC_EXECUTED",
            "reason": update_info["reason"],
            "result": sync_result
        }
    else:
        logger.info(f"Catalog is up to date (Last synced: {update_info['last_sync']}). No action required.")
        return {
            "action": "SKIPPED_UP_TO_DATE",
            "last_sync": update_info["last_sync"],
            "meta": update_info["meta"]
        }


if __name__ == "__main__":
    force_run = "--force" in sys.argv
    no_backup = "--no-backup" in sys.argv
    res = run_auto_update_job(force=force_run, create_backup=not no_backup)
    print(json.dumps(res, indent=2, ensure_ascii=False))
