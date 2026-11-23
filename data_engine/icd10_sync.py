"""
ICD-10 Vietnam & WHO 2019 Catalog Ingestion & Sync Engine
Parses official 15,800+ ICD-10 codes with full BHYT compliance and xuất toán regulatory flags.
"""

import os
import io
import csv
import logging
import urllib.request
import sqlite3
from typing import Optional, Dict, Any, Tuple

logger = logging.getLogger("bhyt.icd10_sync")

ICD10_OFFICIAL_URL = "https://raw.githubusercontent.com/tamton23/primekg-vn-icd10-omop/main/icd10_danh_muc.csv"
RAW_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "raw")
LOCAL_ICD10_CACHE = os.path.join(RAW_DATA_DIR, "icd10_danh_muc.csv")


def download_icd10_csv(url: str = ICD10_OFFICIAL_URL, target_path: str = LOCAL_ICD10_CACHE, force: bool = False) -> str:
    """Download official ICD-10 catalog and cache locally."""
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    if os.path.exists(target_path) and not force and os.path.getsize(target_path) > 1_000_000:
        logger.info(f"Using cached ICD-10 CSV at {target_path} ({os.path.getsize(target_path)} bytes)")
        return target_path

    logger.info(f"Downloading official Vietnamese ICD-10 dataset from: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (BHYT Copilot/1.0)"})
    with urllib.request.urlopen(req, timeout=45) as resp, open(target_path, "wb") as f:
        while chunk := resp.read(65536):
            f.write(chunk)
    logger.info(f"Downloaded and cached ICD-10 dataset ({os.path.getsize(target_path)} bytes)")
    return target_path


def parse_and_sync_icd10(conn: sqlite3.Connection, csv_path: Optional[str] = None, force_download: bool = False) -> Dict[str, Any]:
    """Parse the official CSV and update SQLite database."""
    file_path = csv_path or LOCAL_ICD10_CACHE
    if not os.path.exists(file_path) or force_download:
        file_path = download_icd10_csv(target_path=file_path, force=force_download)

    logger.info(f"Parsing ICD-10 catalog from {file_path}...")
    c = conn.cursor()

    batch = []
    total_parsed = 0
    not_allowed_primary_cnt = 0
    must_use_subcode_cnt = 0
    female_cnt = 0
    male_cnt = 0

    with open(file_path, "r", encoding="utf-8-sig", errors="ignore") as f:
        reader = csv.reader(f)
        # Skip top header rows
        for _ in range(4):
            next(reader, None)

        for row_idx, r in enumerate(reader):
            if len(r) < 22:
                continue

            code = r[17].strip().replace("\n", "")
            if not code:
                continue

            code_nodot = r[18].strip().replace("\n", "") if len(r) > 18 and r[18].strip() else code.replace(".", "")
            name_en = r[19].strip().replace("\n", " ") if len(r) > 19 else ""
            name_vn = r[21].strip().replace("\n", " ") if len(r) > 21 else ""

            if not name_vn:
                continue

            chapter_code = r[2].strip().replace("\n", " ") if len(r) > 2 else ""
            chapter_name = r[4].strip().replace("\n", " ") if len(r) > 4 else ""
            block_code = r[5].strip().replace("\n", " ") if len(r) > 5 else ""
            block_name = r[7].strip().replace("\n", " ") if len(r) > 7 else ""
            sub_category_3 = r[14].strip().replace("\n", " ") if len(r) > 14 else ""

            not_allowed_primary = 1 if len(r) > 23 and r[23].strip() else 0
            not_recommended_primary = 1 if len(r) > 24 and r[24].strip() else 0
            must_use_subcode = 1 if len(r) > 25 and r[25].strip() else 0
            mortality_coding_only = 1 if len(r) > 26 and r[26].strip() else 0
            female_only = 1 if len(r) > 27 and r[27].strip() else 0
            male_only = 1 if len(r) > 28 and r[28].strip() else 0

            if not_allowed_primary:
                not_allowed_primary_cnt += 1
            if must_use_subcode:
                must_use_subcode_cnt += 1
            if female_only:
                female_cnt += 1
            if male_only:
                male_cnt += 1

            batch.append((
                code,
                code_nodot,
                name_vn,
                name_en,
                chapter_code,
                chapter_name,
                block_code,
                block_name,
                sub_category_3,
                not_allowed_primary,
                not_recommended_primary,
                must_use_subcode,
                mortality_coding_only,
                female_only,
                male_only
            ))

            if len(batch) >= 1000:
                c.executemany("""
                INSERT OR REPLACE INTO icd10 (
                    code, code_nodot, name_vn, name_en,
                    chapter_code, chapter_name, block_code, block_name, sub_category_3,
                    not_allowed_primary, not_recommended_primary, must_use_subcode,
                    mortality_coding_only, female_only, male_only
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, batch)
                total_parsed += len(batch)
                batch = []

        if batch:
            c.executemany("""
            INSERT OR REPLACE INTO icd10 (
                code, code_nodot, name_vn, name_en,
                chapter_code, chapter_name, block_code, block_name, sub_category_3,
                not_allowed_primary, not_recommended_primary, must_use_subcode,
                mortality_coding_only, female_only, male_only
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, batch)
            total_parsed += len(batch)

    conn.commit()
    logger.info(f"Successfully synced {total_parsed} ICD-10 records.")
    return {
        "status": "SUCCESS",
        "total_synced": total_parsed,
        "not_allowed_primary": not_allowed_primary_cnt,
        "must_use_subcode": must_use_subcode_cnt,
        "female_only": female_cnt,
        "male_only": male_cnt
    }
