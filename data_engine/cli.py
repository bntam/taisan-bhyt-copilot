"""
CLI Administration & Query Tool for BHYT Clinical Copilot Catalog
Supports fast lookups, status checks, audit evaluations, and automated sync.
"""

import sys
import os
import argparse
import json

# Ensure parent path is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from data_engine.db import get_connection, DB_PATH
from data_engine.updater import check_for_updates, execute_full_sync, get_sync_metadata
from mcp_server.server import validate_prescription, search_icd10, suggest_clinical_note


def cmd_status(args):
    """Display catalog synchronization status and record metrics."""
    meta = get_sync_metadata()
    up = check_for_updates()
    print("=" * 60)
    print("🏥 BHYT CLINICAL COPILOT — CATALOG STATUS")
    print("=" * 60)
    print(f"Catalog DB:     {DB_PATH}")
    print(f"Version:        {meta.get('version', '1.0.0')}")
    print(f"Last Sync:      {meta.get('last_sync', 'Never')}")
    print(f"Remote Check:   {'Available' if up['remote_status']['available'] else 'Unreachable'}")
    print(f"Update Needed:  {up['update_needed']} ({up['reason']})")
    print("-" * 60)
    print("RECORD COUNTS:")
    for cat, cnt in meta.get("counts", {}).items():
        print(f"  • {cat:<22}: {cnt:>6} records")
    print("=" * 60)


def cmd_sync(args):
    """Execute catalog sync and re-index."""
    print("Starting BHYT catalog synchronization...")
    res = execute_full_sync(force_download=args.force, create_backup=not args.no_backup)
    print(f"Sync Result: {res['status']}")
    print(f"Timestamp:   {res['timestamp']}")
    if res.get("backup_path"):
        print(f"Backup:      {res['backup_path']}")
    print("Counts:")
    for cat, cnt in res.get("counts", {}).items():
        print(f"  - {cat}: {cnt}")


def cmd_search(args):
    """Search catalog using FTS5."""
    conn = get_connection()
    c = conn.cursor()
    target = args.target.lower()
    query = args.query.strip()

    if target in ["icd", "icd10"]:
        c.execute("""
        SELECT code, name_vn, name_en, chapter_name
        FROM icd10_fts
        WHERE icd10_fts MATCH ?
        LIMIT ?
        """, (query, args.limit))
        rows = c.fetchall()
        print(f"Found {len(rows)} ICD-10 matches for '{query}':")
        for r in rows:
            print(f"  [{r['code']}] {r['name_vn']} ({r['name_en']})")

    elif target in ["drug", "thuoc"]:
        c.execute("""
        SELECT ten_hoat_chat, ma_hoat_chat, dieu_kien_thanh_toan, ghi_chu_xuat_toan
        FROM thuoc_bhyt_fts
        WHERE thuoc_bhyt_fts MATCH ?
        LIMIT ?
        """, (query, args.limit))
        rows = c.fetchall()
        print(f"Found {len(rows)} Drug matches for '{query}':")
        for r in rows:
            print(f"  • {r['ten_hoat_chat']} ({r['ma_hoat_chat']}): {r['dieu_kien_thanh_toan'][:80]}...")

    elif target in ["tcm", "yhct", "herb"]:
        c.execute("""
        SELECT ten_vi_thuoc, cong_dung, tuong_tac_tay_y
        FROM thuoc_yhct_fts
        WHERE thuoc_yhct_fts MATCH ?
        LIMIT ?
        """, (query, args.limit))
        rows = c.fetchall()
        print(f"Found {len(rows)} TCM Herb matches for '{query}':")
        for r in rows:
            print(f"  • {r['ten_vi_thuoc']}: {r['cong_dung']}")
            if r['tuong_tac_tay_y']:
                print(f"    ⚠️ Cảnh báo Tây Y: {r['tuong_tac_tay_y']}")

    elif target in ["proc", "procedure", "thuthuat"]:
        c.execute("""
        SELECT ten_dich_vu, chuyen_khoa, dieu_kien_chi_dinh
        FROM thu_thuat_bhyt_fts
        WHERE thu_thuat_bhyt_fts MATCH ?
        LIMIT ?
        """, (query, args.limit))
        rows = c.fetchall()
        print(f"Found {len(rows)} Procedure matches for '{query}':")
        for r in rows:
            print(f"  • [{r['chuyen_khoa']}] {r['ten_dich_vu']}: {r['dieu_kien_chi_dinh']}")

    else:
        print(f"Unknown search target: {target}. Choose from: icd, drug, herb, proc")


def cmd_audit(args):
    """Run interactive prescription & procedure audit."""
    drugs = [d.strip() for d in args.drugs.split(",")] if args.drugs else []
    procs = [p.strip() for p in args.procedures.split(",")] if args.procedures else []
    labs = [l.strip() for l in args.labs.split(",")] if args.labs else []

    res = validate_prescription(
        icd_code=args.icd,
        drugs=drugs,
        hospital_level=args.level,
        procedures=procs,
        lab_tests=labs,
        procedure_days=args.days
    )

    print("=" * 60)
    print(f"BHYT AUDIT RESULT: [{res['status']}]")
    print(f"ICD-10:          {res['icd_code']} — {res['disease_name']}")
    print(f"Hospital Level:  {args.level} (Tuyến phòng khám/BV)")
    print(f"High Risk Alerts:{res['high_risk_count']}")
    print("=" * 60)

    if res["alerts"]:
        for idx, a in enumerate(res["alerts"], 1):
            icon = "🔴" if a["severity"] == "HIGH" else "🟡"
            print(f"\n{icon} [{idx}] {a['title']} ({a['rule']})")
            print(f"   Chi tiết: {a['detail']}")
            print(f"   Khắc phục: {a['remedy']}")
    else:
        print("✅ Đơn thuốc và chỉ định thủ thuật hoàn toàn hợp lệ, không có nguy cơ xuất toán!")


def main():
    parser = argparse.ArgumentParser(description="BHYT Clinical Copilot CLI Engine")
    subparsers = parser.add_subparsers(dest="command", help="Sub-commands")

    # status
    p_status = subparsers.add_parser("status", help="Show catalog status")
    p_status.set_defaults(func=cmd_status)

    # sync
    p_sync = subparsers.add_parser("sync", help="Synchronize catalogs")
    p_sync.add_argument("--force", action="store_true", help="Force re-download")
    p_sync.add_argument("--no-backup", action="store_true", help="Skip backup creation")
    p_sync.set_defaults(func=cmd_sync)

    # search
    p_search = subparsers.add_parser("search", help="Search catalog via FTS5")
    p_search.add_argument("target", choices=["icd", "drug", "herb", "proc"], help="Target catalog")
    p_search.add_argument("query", help="Search query string")
    p_search.add_argument("--limit", type=int, default=5, help="Result limit")
    p_search.set_defaults(func=cmd_search)

    # audit
    p_audit = subparsers.add_parser("audit", help="Audit prescription & procedure")
    p_audit.add_argument("--icd", required=True, help="ICD-10 code (e.g. M54.5, E11.9)")
    p_audit.add_argument("--drugs", default="", help="Comma-separated drug names")
    p_audit.add_argument("--procedures", default="", help="Comma-separated procedures")
    p_audit.add_argument("--labs", default="", help="Comma-separated lab tests")
    p_audit.add_argument("--level", default="4", choices=["1", "2", "3", "4"], help="Hospital level (4=Clinic)")
    p_audit.add_argument("--days", type=int, default=1, help="Treatment episode day count")
    p_audit.set_defaults(func=cmd_audit)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
