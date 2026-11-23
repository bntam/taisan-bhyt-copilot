"""
Database Management & FTS5 Full-Text Search Engine for BHYT Catalog
Provides SQLite connection factory, schema creation, safe migrations, FTS5 virtual tables, and triggers.
"""

import os
import sqlite3
from typing import Optional

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
DB_PATH = os.path.join(DATA_DIR, "bhyt_catalog.db")
BACKUP_DIR = os.path.join(DATA_DIR, "backups")


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

    # 8. FTS5 Virtual Tables cho tìm kiếm toàn văn siêu tốc
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

    conn.commit()


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

    conn.commit()
