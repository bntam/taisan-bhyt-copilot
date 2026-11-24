"""
Database Management & FTS5 Full-Text Search Engine for BHYT Catalog
Provides SQLite connection factory, schema creation, safe migrations, FTS5 virtual tables, and triggers.
"""

import os
import json
import hashlib
import sqlite3
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(REPO_ROOT, "data")
DB_PATH = os.path.join(DATA_DIR, "bhyt_catalog.db")
BACKUP_DIR = os.path.join(DATA_DIR, "backups")
METADATA_PATH = os.path.join(DATA_DIR, "sync_metadata.json")
EXTENSION_CATALOG_PATH = os.environ.get(
    "BHYT_EXTENSION_CATALOG_PATH",
    os.path.join(REPO_ROOT, "extension", "data", "catalog.json"),
)
CATALOG_SCHEMA_VERSION = "2.0.0"

# Natural keys used to de-duplicate seed tables (they use AUTOINCREMENT ids, so
# INSERT OR REPLACE without a unique key silently appended a copy on every sync).
_NATURAL_KEYS = {
    "thuoc_bhyt": "COALESCE(ma_hoat_chat, ''), ten_hoat_chat, COALESCE(ham_luong, ''), COALESCE(duong_dung, '')",
    "thuoc_yhct": "COALESCE(ma_vi_thuoc, ''), ten_vi_thuoc",
    "yhct_icd10_mapping": "COALESCE(ma_benh_yhct, ''), ten_chung_trang, ma_icd10_tuong_duong",
}


def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Return a configured SQLite connection with foreign keys and Row factory."""
    path = db_path or DB_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def _ensure_columns(conn: sqlite3.Connection, table: str, expected_cols: dict) -> None:
    """Add missing columns to an existing table dynamically."""
    c = conn.cursor()
    c.execute(f"PRAGMA table_info({table})")
    existing_cols = {row["name"]: row for row in c.fetchall()}
    for col_name, col_type in expected_cols.items():
        if col_name not in existing_cols:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}")
    conn.commit()


def init_schema(conn: sqlite3.Connection) -> None:
    """Initialize all normalized tables, indexes, and FTS5 search tables."""
    c = conn.cursor()

    # 1. Bảng ICD-10 mở rộng đầy đủ quy chuẩn Bộ Y tế & WHO 2019
    c.execute("""
    CREATE TABLE IF NOT EXISTS icd10 (
        code TEXT PRIMARY KEY,
        code_nodot TEXT NOT NULL,
        name_vn TEXT NOT NULL,
        name_en TEXT,
        chapter_code TEXT,
        chapter_name TEXT,
        block_code TEXT,
        block_name TEXT,
        sub_category_3 TEXT,
        not_allowed_primary INTEGER DEFAULT 0,
        not_recommended_primary INTEGER DEFAULT 0,
        must_use_subcode INTEGER DEFAULT 0,
        mortality_coding_only INTEGER DEFAULT 0,
        female_only INTEGER DEFAULT 0,
        male_only INTEGER DEFAULT 0
    )
    """)

    _ensure_columns(conn, "icd10", {
        "chapter_code": "TEXT",
        "block_code": "TEXT",
        "sub_category_3": "TEXT",
        "not_recommended_primary": "INTEGER DEFAULT 0",
        "mortality_coding_only": "INTEGER DEFAULT 0",
        "female_only": "INTEGER DEFAULT 0",
        "male_only": "INTEGER DEFAULT 0"
    })

    c.execute("CREATE INDEX IF NOT EXISTS idx_icd10_code_nodot ON icd10(code_nodot)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_icd10_name_vn ON icd10(name_vn)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_icd10_block ON icd10(block_code)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_icd10_subcode ON icd10(must_use_subcode)")

    # 2. Bảng Thuốc Tân Dược BHYT (Thông tư 20/2022/TT-BYT & QĐ 7603/QĐ-BYT)
    c.execute("""
    CREATE TABLE IF NOT EXISTS thuoc_bhyt (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ma_hoat_chat TEXT,
        ten_hoat_chat TEXT NOT NULL,
        nhom_duoc_ly TEXT,
        duong_dung TEXT,
        ham_luong TEXT,
        hang_bv_duoc_ke TEXT DEFAULT '1,2,3,4',
        ty_le_thanh_toan INTEGER DEFAULT 100,
        dieu_kien_thanh_toan TEXT,
        ghi_chu_xuat_toan TEXT,
        yeu_cau_can_lam_sang TEXT
    )
    """)

    _ensure_columns(conn, "thuoc_bhyt", {
        "nhom_duoc_ly": "TEXT",
        "yeu_cau_can_lam_sang": "TEXT"
    })

    c.execute("CREATE INDEX IF NOT EXISTS idx_thuoc_hoat_chat ON thuoc_bhyt(ten_hoat_chat)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_thuoc_hang_bv ON thuoc_bhyt(hang_bv_duoc_ke)")

    # 3. Bảng Thuốc & Vị thuốc YHCT (Thông tư 27/2020/TT-BYT & TT 05/2015/TT-BYT)
    c.execute("""
    CREATE TABLE IF NOT EXISTS thuoc_yhct (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ma_vi_thuoc TEXT,
        ten_vi_thuoc TEXT NOT NULL,
        ten_khoa_hoc TEXT,
        bo_phan_dung TEXT,
        tinh_vi_quy_kinh TEXT,
        cong_dung TEXT,
        chong_chi_dinh TEXT,
        hang_bv_duoc_ke TEXT DEFAULT '1,2,3,4',
        ty_le_thanh_toan INTEGER DEFAULT 100,
        tuong_tac_tay_y TEXT
    )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_yhct_ten ON thuoc_yhct(ten_vi_thuoc)")

    # 4. Bảng Dịch Vụ / Thủ Thuật BHYT (Thông tư 13/2019, TT 39/2018, TT 13/2023)
    c.execute("""
    CREATE TABLE IF NOT EXISTS thu_thuat_bhyt (
        ma_dich_vu TEXT PRIMARY KEY,
        ten_dich_vu TEXT NOT NULL,
        chuyen_khoa TEXT,
        gia_bhyt REAL,
        dinh_muc_ngay INTEGER DEFAULT 1,
        so_ngay_toi_da INTEGER DEFAULT 15,
        dieu_kien_chi_dinh TEXT,
        icd_phu_hop TEXT
    )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_thu_thuat_ten ON thu_thuat_bhyt(ten_dich_vu)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_thu_thuat_khoa ON thu_thuat_bhyt(chuyen_khoa)")

    # 5. Bảng Ánh xạ Chứng trạng YHCT <-> ICD-10 (Quyết định 4443/QĐ-BYT)
    c.execute("""
    CREATE TABLE IF NOT EXISTS yhct_icd10_mapping (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ma_benh_yhct TEXT,
        ten_chung_trang TEXT NOT NULL,
        bat_cuong_tang_phu TEXT,
        ma_icd10_tuong_duong TEXT NOT NULL,
        ten_benh_tay_y TEXT,
        trieu_chung_vong_van_van_thiet TEXT,
        phap_tri_de_xuat TEXT
    )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_map_icd ON yhct_icd10_mapping(ma_icd10_tuong_duong)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_map_chung ON yhct_icd10_mapping(ten_chung_trang)")

    # 6. Bảng Quy Tắc Xuất Toán (BHYT Audit Rules)
    c.execute("""
    CREATE TABLE IF NOT EXISTS xuat_toan_rules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rule_code TEXT UNIQUE,
        rule_type TEXT,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        severity TEXT NOT NULL,
        legal_basis TEXT,
        remedy_suggestion TEXT
    )
    """)

    _ensure_columns(conn, "xuat_toan_rules", {
        "legal_basis": "TEXT"
    })

    c.execute("CREATE INDEX IF NOT EXISTS idx_rules_type ON xuat_toan_rules(rule_type)")

    # 6b. Bảng Quy Chuẩn Giám Định XML 130 / QĐ 130/QĐ-BYT
    c.execute("""
    CREATE TABLE IF NOT EXISTS xml130_rules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rule_code TEXT UNIQUE,
        category TEXT,
        table_name TEXT,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        severity TEXT NOT NULL,
        legal_basis TEXT
    )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_xml130_cat ON xml130_rules(category)")

    # 7. Bảng Metadata Lịch sử Đồng bộ
    c.execute("""
    CREATE TABLE IF NOT EXISTS sync_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        synced_at TEXT NOT NULL,
        source_name TEXT NOT NULL,
        version TEXT,
        record_count INTEGER,
        sha256_hash TEXT,
        status TEXT
    )
    """)

    # 8. Bảng Danh mục Cơ sở KCB BHYT (mã CSKCB 5 ký tự theo BHXH Việt Nam)
    c.execute("""
    CREATE TABLE IF NOT EXISTS cskcb (
        ma_cskcb TEXT PRIMARY KEY,
        ten_cskcb TEXT NOT NULL,
        tuyen TEXT NOT NULL,
        hang_bv TEXT,
        tinh TEXT,
        loai_hinh TEXT
    )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_cskcb_tuyen ON cskcb(tuyen)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_cskcb_tinh ON cskcb(tinh)")

    dedupe_seed_tables(conn)

    # 9. FTS5 Virtual Tables cho tìm kiếm toàn văn siêu tốc
    c.execute("""
    CREATE VIRTUAL TABLE IF NOT EXISTS icd10_fts USING fts5(
        code,
        name_vn,
        name_en,
        chapter_name,
        block_name,
        tokenize = 'unicode61 remove_diacritics 2'
    )
    """)

    c.execute("""
    CREATE VIRTUAL TABLE IF NOT EXISTS thuoc_bhyt_fts USING fts5(
        ten_hoat_chat,
        ma_hoat_chat,
        dieu_kien_thanh_toan,
        ghi_chu_xuat_toan,
        tokenize = 'unicode61 remove_diacritics 2'
    )
    """)

    c.execute("""
    CREATE VIRTUAL TABLE IF NOT EXISTS thuoc_yhct_fts USING fts5(
        ten_vi_thuoc,
        cong_dung,
        tinh_vi_quy_kinh,
        tuong_tac_tay_y,
        tokenize = 'unicode61 remove_diacritics 2'
    )
    """)

    c.execute("""
    CREATE VIRTUAL TABLE IF NOT EXISTS thu_thuat_bhyt_fts USING fts5(
        ten_dich_vu,
        chuyen_khoa,
        dieu_kien_chi_dinh,
        tokenize = 'unicode61 remove_diacritics 2'
    )
    """)

    c.execute("""
    CREATE VIRTUAL TABLE IF NOT EXISTS cskcb_fts USING fts5(
        ma_cskcb,
        ten_cskcb,
        tinh,
        loai_hinh,
        tokenize = 'unicode61 remove_diacritics 2'
    )
    """)

    conn.commit()


def dedupe_seed_tables(conn: sqlite3.Connection) -> Dict[str, int]:
    """Remove duplicated seed rows (keep the oldest id) and enforce natural-key uniqueness.

    Returns the number of rows removed per table.
    """
    c = conn.cursor()
    removed: Dict[str, int] = {}
    for table, key_expr in _NATURAL_KEYS.items():
        c.execute(f"""
            DELETE FROM {table}
            WHERE id NOT IN (SELECT MIN(id) FROM {table} GROUP BY {key_expr})
        """)
        removed[table] = c.rowcount
        c.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS uq_{table}_natural ON {table}({key_expr})")
    conn.commit()
    return removed


def rebuild_fts_indexes(conn: sqlite3.Connection) -> None:
    """Populate / Rebuild all FTS5 tables from the main relational tables."""
    c = conn.cursor()
    c.execute("DROP TABLE IF EXISTS icd10_fts")
    c.execute("""
    CREATE VIRTUAL TABLE icd10_fts USING fts5(
        code,
        name_vn,
        name_en,
        chapter_name,
        block_name,
        tokenize = 'unicode61 remove_diacritics 2'
    )
    """)
    c.execute("""
    INSERT INTO icd10_fts (code, name_vn, name_en, chapter_name, block_name)
    SELECT code, name_vn, COALESCE(name_en, ''), COALESCE(chapter_name, ''), COALESCE(block_name, '')
    FROM icd10
    """)

    c.execute("DROP TABLE IF EXISTS thuoc_bhyt_fts")
    c.execute("""
    CREATE VIRTUAL TABLE thuoc_bhyt_fts USING fts5(
        ten_hoat_chat,
        ma_hoat_chat,
        dieu_kien_thanh_toan,
        ghi_chu_xuat_toan,
        tokenize = 'unicode61 remove_diacritics 2'
    )
    """)
    c.execute("""
    INSERT INTO thuoc_bhyt_fts (ten_hoat_chat, ma_hoat_chat, dieu_kien_thanh_toan, ghi_chu_xuat_toan)
    SELECT ten_hoat_chat, COALESCE(ma_hoat_chat, ''), COALESCE(dieu_kien_thanh_toan, ''), COALESCE(ghi_chu_xuat_toan, '')
    FROM thuoc_bhyt
    """)

    c.execute("DROP TABLE IF EXISTS thuoc_yhct_fts")
    c.execute("""
    CREATE VIRTUAL TABLE thuoc_yhct_fts USING fts5(
        ten_vi_thuoc,
        cong_dung,
        tinh_vi_quy_kinh,
        tuong_tac_tay_y,
        tokenize = 'unicode61 remove_diacritics 2'
    )
    """)
    c.execute("""
    INSERT INTO thuoc_yhct_fts (ten_vi_thuoc, cong_dung, tinh_vi_quy_kinh, tuong_tac_tay_y)
    SELECT ten_vi_thuoc, COALESCE(cong_dung, ''), COALESCE(tinh_vi_quy_kinh, ''), COALESCE(tuong_tac_tay_y, '')
    FROM thuoc_yhct
    """)

    c.execute("DROP TABLE IF EXISTS thu_thuat_bhyt_fts")
    c.execute("""
    CREATE VIRTUAL TABLE thu_thuat_bhyt_fts USING fts5(
        ten_dich_vu,
        chuyen_khoa,
        dieu_kien_chi_dinh,
        tokenize = 'unicode61 remove_diacritics 2'
    )
    """)
    c.execute("""
    INSERT INTO thu_thuat_bhyt_fts (ten_dich_vu, chuyen_khoa, dieu_kien_chi_dinh)
    SELECT ten_dich_vu, COALESCE(chuyen_khoa, ''), COALESCE(dieu_kien_chi_dinh, '')
    FROM thu_thuat_bhyt
    """)

    c.execute("DROP TABLE IF EXISTS cskcb_fts")
    c.execute("""
    CREATE VIRTUAL TABLE cskcb_fts USING fts5(
        ma_cskcb,
        ten_cskcb,
        tinh,
        loai_hinh,
        tokenize = 'unicode61 remove_diacritics 2'
    )
    """)
    c.execute("""
    INSERT INTO cskcb_fts (ma_cskcb, ten_cskcb, tinh, loai_hinh)
    SELECT ma_cskcb, ten_cskcb, COALESCE(tinh, ''), COALESCE(loai_hinh, '')
    FROM cskcb
    """)

    conn.commit()


# ---------------------------------------------------------------------------
# Extension catalog export (extension/data/catalog.json + /api/catalog-bundle)
# ---------------------------------------------------------------------------

_ICD_FLAG_COLUMNS = (
    "not_allowed_primary",
    "not_recommended_primary",
    "must_use_subcode",
    "mortality_coding_only",
    "female_only",
    "male_only",
)

_EXPORT_TABLES = {
    "thuoc_bhyt": "SELECT * FROM thuoc_bhyt ORDER BY id",
    "thuoc_yhct": "SELECT * FROM thuoc_yhct ORDER BY id",
    "thu_thuat_bhyt": "SELECT * FROM thu_thuat_bhyt ORDER BY ma_dich_vu",
    "cskcb": "SELECT * FROM cskcb ORDER BY tuyen, ma_cskcb",
    "xuat_toan_rules": "SELECT * FROM xuat_toan_rules ORDER BY id",
    "xml130_rules": "SELECT * FROM xml130_rules ORDER BY id",
    "yhct_icd10_mapping": "SELECT * FROM yhct_icd10_mapping ORDER BY id",
}


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).fetchone()
    return row is not None


def _read_metadata_file(path: str = METADATA_PATH) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _export_icd10(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """ICD-10 rows in the legacy 4-field shape; regulatory flags are added only when set."""
    rows = []
    for r in conn.execute("SELECT * FROM icd10 ORDER BY code"):
        item = {
            "code": r["code"],
            "name_vn": r["name_vn"],
            "name_en": r["name_en"],
            "chapter_name": r["chapter_name"],
        }
        for flag in _ICD_FLAG_COLUMNS:
            if r[flag]:
                item[flag] = 1
        rows.append(item)
    return rows


def build_extension_catalog(db_path: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Build the extension catalog bundle in memory.

    Keeps the v1 keys (version, updated_at, icd10, thuoc_bhyt, thuoc_yhct, thu_thuat_bhyt,
    xuat_toan_rules) so the shipped extension keeps working, and adds cskcb,
    yhct_icd10_mapping, sync_metadata, catalog_version and counts.
    `catalog_version` is a content hash: it only changes when catalog data changes.
    """
    conn = get_connection(db_path)
    try:
        init_schema(conn)
        sections: Dict[str, Any] = {"icd10": _export_icd10(conn)}
        for key, sql in _EXPORT_TABLES.items():
            sections[key] = [dict(r) for r in conn.execute(sql)] if _table_exists(conn, key) else []
    finally:
        conn.close()

    digest = hashlib.sha256(
        json.dumps(sections, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    meta = metadata if metadata is not None else _read_metadata_file()

    bundle: Dict[str, Any] = {
        "version": CATALOG_SCHEMA_VERSION,
        "catalog_version": digest[:16],
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "counts": {k: len(v) for k, v in sections.items()},
        "sync_metadata": {
            "version": meta.get("version"),
            "last_sync": meta.get("last_sync"),
            "sources": meta.get("sources", []),
        },
    }
    bundle.update(sections)
    return bundle


def export_extension_catalog(
    output_path: Optional[str] = None,
    db_path: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Write the compact catalog JSON for the browser extension atomically.

    Returns {path, catalog_version, counts, size_bytes}.
    """
    path = output_path or EXTENSION_CATALOG_PATH
    bundle = build_extension_catalog(db_path=db_path, metadata=metadata)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(bundle, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp_path, path)
    return {
        "path": path,
        "catalog_version": bundle["catalog_version"],
        "counts": bundle["counts"],
        "size_bytes": os.path.getsize(path),
    }
