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

from .db import (
    get_connection,
    init_schema,
    rebuild_fts_indexes,
    export_extension_catalog,
    DB_PATH,
    DATA_DIR,
    BACKUP_DIR,
    METADATA_PATH,
    EXTENSION_CATALOG_PATH,
    CATALOG_SCHEMA_VERSION,
)
from .icd10_sync import parse_and_sync_icd10, ICD10_OFFICIAL_URL, LOCAL_ICD10_CACHE
from .thuoc_tt20_sync import sync_thuoc_bhyt
from .thu_thuat_tt13_sync import sync_thu_thuat_bhyt
from .yhct_tt27_sync import sync_thuoc_yhct, sync_yhct_icd10_mapping
from .xuat_toan_rules_sync import sync_xuat_toan_rules
from .cskcb_sync import sync_cskcb

logger = logging.getLogger("bhyt.updater")

CATALOG_SOURCES = [
    "Thông tư 20/2022/TT-BYT (Thuốc Tân Dược)",
    "Thông tư 27/2020/TT-BYT (Thuốc & Vị thuốc YHCT)",
    "Thông tư 13/2019/TT-BYT (Giá & Định mức Dịch vụ Kỹ thuật)",
    "Quyết định 4443/QĐ-BYT (Mã hóa Bệnh học Y học Cổ truyền)",
    "Danh mục ICD-10 Chuẩn hóa Quốc gia (WHO / Cổng BYT 2019)",
    "Danh mục Cơ sở KCB BHYT (mã CSKCB - BHXH Việt Nam)",
]
COUNTED_TABLES = (
    "icd10",
    "thuoc_bhyt",
    "thu_thuat_bhyt",
    "thuoc_yhct",
    "yhct_icd10_mapping",
    "xuat_toan_rules",
    "cskcb",
)


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
        "version": CATALOG_SCHEMA_VERSION,
        "last_sync": None,
        "sha256": None,
        "counts": {},
        "sources": list(CATALOG_SOURCES),
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


def count_catalog_records(conn: sqlite3.Connection) -> Dict[str, int]:
    """Row counts for every catalog table."""
    return {t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in COUNTED_TABLES}


def execute_full_sync(
    force_download: bool = False,
    create_backup: bool = True,
    export_catalog: bool = True,
    catalog_output_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute the complete ingestion pipeline, rebuild FTS indexes and re-export
    the extension catalog bundle (extension/data/catalog.json by default)."""
    logger.info("Starting BHYT Catalog full synchronization...")
    os.makedirs(DATA_DIR, exist_ok=True)

    backup_taken = None
    if create_backup and os.path.exists(DB_PATH):
        backup_taken = create_database_backup(DB_PATH)

    conn = get_connection(DB_PATH)
    try:
        init_schema(conn)

        stats = {
            "icd10": parse_and_sync_icd10(conn, force_download=force_download),
            "thuoc_bhyt": sync_thuoc_bhyt(conn),
            "thu_thuat_bhyt": sync_thu_thuat_bhyt(conn),
            "thuoc_yhct": sync_thuoc_yhct(conn),
            "yhct_icd10_mapping": sync_yhct_icd10_mapping(conn),
            "xuat_toan_rules": sync_xuat_toan_rules(conn),
            "cskcb": sync_cskcb(conn),
        }
        logger.debug(f"Per-source sync stats: {stats}")

        rebuild_fts_indexes(conn)
        counts = count_catalog_records(conn)

        remote_status = check_remote_source_status()
        db_sha256 = compute_file_sha256(DB_PATH)
        now_iso = datetime.now().isoformat()

        conn.execute("""
        INSERT INTO sync_history (synced_at, source_name, version, record_count, sha256_hash, status)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (now_iso, "BHYT_MULTI_CATALOG", CATALOG_SCHEMA_VERSION, sum(counts.values()), db_sha256, "SUCCESS"))
        conn.commit()
    finally:
        conn.close()

    meta = {
        "version": CATALOG_SCHEMA_VERSION,
        "last_sync": now_iso,
        "db_sha256": db_sha256,
        "remote_etag": remote_status.get("etag", ""),
        "backup_path": backup_taken,
        "counts": counts,
        "sources": list(CATALOG_SOURCES),
    }

    catalog_export = None
    if export_catalog:
        try:
            catalog_export = export_extension_catalog(
                output_path=catalog_output_path or EXTENSION_CATALOG_PATH,
                db_path=DB_PATH,
                metadata=meta,
            )
            meta["catalog_version"] = catalog_export["catalog_version"]
            logger.info(f"Exported extension catalog -> {catalog_export['path']} ({catalog_export['size_bytes']} bytes)")
        except OSError as e:
            logger.error(f"Extension catalog export failed: {e}")
            catalog_export = {"error": str(e)}

    save_sync_metadata(meta)

    logger.info(f"Sync complete. Counts: {counts}")
    return {
        "status": "SUCCESS",
        "timestamp": now_iso,
        "counts": counts,
        "backup_path": backup_taken,
        "catalog_export": catalog_export,
    }
