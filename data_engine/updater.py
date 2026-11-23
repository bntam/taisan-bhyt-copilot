"""
Automated BHYT Catalog Update Engine
Orchestrates remote checksum checks, automated delta sync, database backup snapshots,
offline fallback mechanisms, and FTS5 index reconstruction.
"""

import os
import sys
import json
import shutil
import hashlib
import logging
import sqlite3
import urllib.request
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, List

from .db import get_connection, init_schema, rebuild_fts_indexes, DB_PATH, DATA_DIR, BACKUP_DIR
from .icd10_sync import parse_and_sync_icd10, ICD10_OFFICIAL_URL, LOCAL_ICD10_CACHE
from .thuoc_tt20_sync import sync_thuoc_bhyt
from .thu_thuat_tt13_sync import sync_thu_thuat_bhyt
from .yhct_tt27_sync import sync_thuoc_yhct, sync_yhct_icd10_mapping
from .xuat_toan_rules_sync import sync_xuat_toan_rules

logger = logging.getLogger("bhyt.updater")
METADATA_PATH = os.path.join(DATA_DIR, "sync_metadata.json")


def compute_file_sha256(path: str) -> str:
    """Compute sha256 hash of a file."""
    if not os.path.exists(path):
        return ""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def check_remote_source_status(url: str = ICD10_OFFICIAL_URL) -> Dict[str, Any]:
    """Check remote dataset status via HTTP HEAD request."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (BHYT Auto-Updater)"}, method="HEAD")
        with urllib.request.urlopen(req, timeout=10) as resp:
            etag = resp.headers.get("ETag", "")
            last_modified = resp.headers.get("Last-Modified", "")
            content_length = resp.headers.get("Content-Length", 0)
            return {
                "available": True,
                "etag": etag,
                "last_modified": last_modified,
                "content_length": int(content_length) if content_length else 0,
                "error": None
            }
    except Exception as e:
        logger.warning(f"Could not reach remote source {url}: {e}")
        return {
            "available": False,
            "etag": "",
            "last_modified": "",
            "content_length": 0,
            "error": str(e)
        }


def create_database_backup(db_path: str = DB_PATH, backup_dir: str = BACKUP_DIR, max_backups: int = 5) -> Optional[str]:
    """Create a point-in-time timestamped backup copy of the SQLite catalog."""
    if not os.path.exists(db_path):
        return None

    os.makedirs(backup_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"bhyt_catalog_{timestamp}.db"
    backup_path = os.path.join(backup_dir, backup_filename)

    shutil.copy2(db_path, backup_path)
    logger.info(f"Created database backup: {backup_path}")

    # Rotate old backups
    try:
        backups = sorted([
            os.path.join(backup_dir, f) for f in os.listdir(backup_dir)
            if f.startswith("bhyt_catalog_") and f.endswith(".db")
        ])
        while len(backups) > max_backups:
            oldest = backups.pop(0)
            os.remove(oldest)
            logger.info(f"Rotated old backup: {oldest}")
    except Exception as e:
        logger.warning(f"Error during backup rotation: {e}")

    return backup_path


def get_sync_metadata() -> Dict[str, Any]:
    """Retrieve stored sync metadata or return default initial structure."""
    if os.path.exists(METADATA_PATH):
        try:
            with open(METADATA_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to read metadata file: {e}")

    return {
        "version": "1.0.0",
        "last_sync": None,
        "sha256": None,
        "counts": {},
        "sources": [
            "Thông tư 20/2022/TT-BYT (Thuốc Tân Dược)",
            "Thông tư 27/2020/TT-BYT (Thuốc & Vị thuốc YHCT)",
            "Thông tư 13/2019/TT-BYT (Giá & Định mức Dịch vụ Kỹ thuật)",
            "Quyết định 4443/QĐ-BYT (Mã hóa Bệnh học Y học Cổ truyền)",
            "Danh mục ICD-10 Chuẩn hóa Quốc gia (WHO / Cổng BYT 2019)"
        ]
    }


def save_sync_metadata(meta: Dict[str, Any]) -> None:
    """Save metadata to JSON file atomically."""
    os.makedirs(os.path.dirname(METADATA_PATH), exist_ok=True)
    temp_path = f"{METADATA_PATH}.tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    os.replace(temp_path, METADATA_PATH)


def check_for_updates() -> Dict[str, Any]:
    """Check if remote sources have newer data than local catalog."""
    meta = get_sync_metadata()
    remote_status = check_remote_source_status()

    has_local_db = os.path.exists(DB_PATH) and os.path.getsize(DB_PATH) > 0
    local_sha = compute_file_sha256(LOCAL_ICD10_CACHE) if os.path.exists(LOCAL_ICD10_CACHE) else None

    update_needed = False
    reason = "up_to_date"

    if not has_local_db:
        update_needed = True
        reason = "no_local_database"
    elif not meta.get("last_sync"):
        update_needed = True
        reason = "initial_sync_required"
    elif remote_status["available"]:
        cached_etag = meta.get("remote_etag")
        if remote_status["etag"] and cached_etag and remote_status["etag"] != cached_etag:
            update_needed = True
            reason = "remote_etag_changed"

    return {
        "update_needed": update_needed,
        "reason": reason,
        "last_sync": meta.get("last_sync"),
        "local_sha256": local_sha,
        "remote_status": remote_status,
        "meta": meta
    }


def execute_full_sync(force_download: bool = False, create_backup: bool = True) -> Dict[str, Any]:
    """Execute complete ingestion pipeline and rebuild indexes."""
    logger.info("Starting BHYT Catalog full synchronization...")
    os.makedirs(DATA_DIR, exist_ok=True)

    backup_taken = None
    if create_backup and os.path.exists(DB_PATH):
        backup_taken = create_database_backup(DB_PATH)

    conn = get_connection(DB_PATH)
    init_schema(conn)

    # 1. Sync ICD-10
    icd_stats = parse_and_sync_icd10(conn, force_download=force_download)

    # 2. Sync Western Drugs
    drug_stats = sync_thuoc_bhyt(conn)

    # 3. Sync Procedures
    proc_stats = sync_thu_thuat_bhyt(conn)

    # 4. Sync TCM Herbs & Mappings
    yhct_stats = sync_thuoc_yhct(conn)
    map_stats = sync_yhct_icd10_mapping(conn)

    # 5. Sync Audit Rules
    rule_stats = sync_xuat_toan_rules(conn)

    # 6. Rebuild FTS5 Virtual Tables
    rebuild_fts_indexes(conn)

    # 7. Collect total records count
    c = conn.cursor()
    c.execute("SELECT count(*) FROM icd10")
    total_icd = c.fetchone()[0]
    c.execute("SELECT count(*) FROM thuoc_bhyt")
    total_drugs = c.fetchone()[0]
    c.execute("SELECT count(*) FROM thu_thuat_bhyt")
    total_procs = c.fetchone()[0]
    c.execute("SELECT count(*) FROM thuoc_yhct")
    total_yhct = c.fetchone()[0]
    c.execute("SELECT count(*) FROM yhct_icd10_mapping")
    total_maps = c.fetchone()[0]
    c.execute("SELECT count(*) FROM xuat_toan_rules")
    total_rules = c.fetchone()[0]

    # Log to sync_history table
    remote_status = check_remote_source_status()
    db_sha256 = compute_file_sha256(DB_PATH)
    now_iso = datetime.now().isoformat()

    c.execute("""
    INSERT INTO sync_history (synced_at, source_name, version, record_count, sha256_hash, status)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (now_iso, "BHYT_MULTI_CATALOG", "1.0.0", total_icd + total_drugs + total_procs + total_yhct, db_sha256, "SUCCESS"))
    conn.commit()
    conn.close()

    # Save metadata JSON
    meta = {
        "version": "1.0.0",
        "last_sync": now_iso,
        "db_sha256": db_sha256,
        "remote_etag": remote_status.get("etag", ""),
        "backup_path": backup_taken,
        "counts": {
            "icd10": total_icd,
            "thuoc_bhyt": total_drugs,
            "thu_thuat_bhyt": total_procs,
            "thuoc_yhct": total_yhct,
            "yhct_icd10_mapping": total_maps,
            "xuat_toan_rules": total_rules
        },
        "sources": [
            "Thông tư 20/2022/TT-BYT (Thuốc Tân Dược)",
            "Thông tư 27/2020/TT-BYT (Thuốc & Vị thuốc YHCT)",
            "Thông tư 13/2019/TT-BYT (Giá & Định mức Dịch vụ Kỹ thuật)",
            "Quyết định 4443/QĐ-BYT (Mã hóa Bệnh học Y học Cổ truyền)",
            "Danh mục ICD-10 Chuẩn hóa Quốc gia (WHO / Cổng BYT 2019)"
        ]
    }
    save_sync_metadata(meta)

    logger.info(f"Sync complete. Total ICD: {total_icd}, Drugs: {total_drugs}, Procedures: {total_procs}, YHCT: {total_yhct}, Rules: {total_rules}")
    return {
        "status": "SUCCESS",
        "timestamp": now_iso,
        "counts": meta["counts"],
        "backup_path": backup_taken
    }
