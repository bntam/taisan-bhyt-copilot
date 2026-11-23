"""
Danh mục Dịch vụ Kỹ thuật, Thủ thuật BHYT YHCT & PHCN (Thông tư 13/2019, TT 39/2018 & TT 22/2023/TT-BYT)
Enforces clinical indications, duration limits, daily ceilings, and compatible ICD-10 sets.
"""

import os
import json
import logging
import sqlite3
from typing import Dict, Any, List, Optional

logger = logging.getLogger("bhyt.thuthuat_sync")

OFFICIAL_TT13_PROCEDURES: List[Dict[str, Any]] = [
    {
        "ma_dich_vu": "TT.YHCT.01",
        "ten_dich_vu": "Điện châm điều trị",
        "chuyen_khoa": "Y học cổ truyền",
        "gia_bhyt": 43600.0,
        "dinh_muc_ngay": 1,
        "so_ngay_toi_da": 15,
        "dieu_kien_chi_dinh": "Bệnh nhân có hội chứng đau (đau lưng, đau vai gáy, liệt ngoại biên). Bắt buộc ghi rõ huyệt châm, tần số, thời gian lưu kim (20-30 phút).",
        "icd_phu_hop": "M54.5, M54.2, G51.0, M47, M51, M79.1"
    },
    {
        "ma_dich_vu": "TT.YHCT.02",
        "ten_dich_vu": "Xoa bóp bấm huyệt điều trị",
        "chuyen_khoa": "Y học cổ truyền",
        "gia_bhyt": 64400.0,
        "dinh_muc_ngay": 1,
        "so_ngay_toi_da": 15,
        "dieu_kien_chi_dinh": "Ghi nhận chỉ định cơ cứng, hạn chế tầm vận động, đau mạn tính. Tối đa 1 lần/ngày, không làm quá 15 ngày/đợt điều trị ngoại trú.",
        "icd_phu_hop": "M54.5, M54.2, M75, M47, M51"
    },
    {
        "ma_dich_vu": "TT.YHCT.03",
        "ten_dich_vu": "Cứu ngải (hoặc chiếu đèn hồng ngoại)",
        "chuyen_khoa": "Y học cổ truyền",
        "gia_bhyt": 26200.0,
        "dinh_muc_ngay": 1,
        "so_ngay_toi_da": 15,
        "dieu_kien_chi_dinh": "Thể bệnh hư hàn, phong hàn thấp trệ. Chống chỉ định vùng da viêm loét, thể nhiệt cấp tính.",
        "icd_phu_hop": "M54.5, M54.2, M79.1, M47"
    },
    {
        "ma_dich_vu": "TT.YHCT.04",
        "ten_dich_vu": "Kéo nắn, kéo dãn cột sống",
        "chuyen_khoa": "Phục hồi chức năng",
        "gia_bhyt": 67000.0,
        "dinh_muc_ngay": 1,
        "so_ngay_toi_da": 10,
        "dieu_kien_chi_dinh": "Bắt buộc có phim X-quang hoặc MRI cột sống xác nhận thoái hóa/thoát vị trước khi chỉ định.",
        "icd_phu_hop": "M51.1, M51.2, M47.8, M54.5"
    },
    {
        "ma_dich_vu": "TT.YHCT.05",
        "ten_dich_vu": "Thủy châm vào huyệt",
        "chuyen_khoa": "Y học cổ truyền",
        "gia_bhyt": 21500.0,
        "dinh_muc_ngay": 1,
        "so_ngay_toi_da": 10,
        "dieu_kien_chi_dinh": "Ghi rõ tên thuốc thủy châm (Vitamin B1, B6, B12 hoặc Novocain), liều lượng và vị trí huyệt thủy châm.",
        "icd_phu_hop": "G51.0, M54.1, M54.2, M54.5"
    },
    {
        "ma_dich_vu": "TT.YHCT.06",
        "ten_dich_vu": "Cấy chỉ điều trị",
        "chuyen_khoa": "Y học cổ truyền",
        "gia_bhyt": 145000.0,
        "dinh_muc_ngay": 1,
        "so_ngay_toi_da": 3,
        "dieu_kien_chi_dinh": "Điều trị bệnh mạn tính định kỳ 2-3 tuần/lần. Ghi rõ loại chỉ catgut/PDO vô khuẩn và danh sách huyệt cấy.",
        "icd_phu_hop": "M54.5, G51.0, J45, K21"
    },
    {
        "ma_dich_vu": "TT.YHCT.07",
        "ten_dich_vu": "Giác hơi điều trị",
        "chuyen_khoa": "Y học cổ truyền",
        "gia_bhyt": 27800.0,
        "dinh_muc_ngay": 1,
        "so_ngay_toi_da": 10,
        "dieu_kien_chi_dinh": "Chứng phong hàn thấp gây co cứng cơ lưng, cổ gáy. Tránh làm trên vùng da tổn thương.",
        "icd_phu_hop": "M54.2, M54.5, M79.1"
    },
    {
        "ma_dich_vu": "TT.PHCN.01",
        "ten_dich_vu": "Siêu âm điều trị",
        "chuyen_khoa": "Phục hồi chức năng",
        "gia_bhyt": 45000.0,
        "dinh_muc_ngay": 1,
        "so_ngay_toi_da": 15,
        "dieu_kien_chi_dinh": "Viêm quanh khớp, viêm điểm bám gân, thoái hóa khớp. Ghi rõ đầu dò và công suất điều trị.",
        "icd_phu_hop": "M75, M77, M54.5, M15-M19"
    },
    {
        "ma_dich_vu": "TT.PHCN.02",
        "ten_dich_vu": "Điện xung điều trị",
        "chuyen_khoa": "Phục hồi chức năng",
        "gia_bhyt": 41000.0,
        "dinh_muc_ngay": 1,
        "so_ngay_toi_da": 15,
        "dieu_kien_chi_dinh": "Giảm đau cục bộ, kích thích thần kinh cơ. Hồ sơ ghi rõ vị trí điện cực và cường độ dòng điện.",
        "icd_phu_hop": "M54.5, M54.2, M79.1, G51.0"
    },
    {
        "ma_dich_vu": "TT.PHCN.03",
        "ten_dich_vu": "Tập vận động có trợ giúp",
        "chuyen_khoa": "Phục hồi chức năng",
        "gia_bhyt": 52000.0,
        "dinh_muc_ngay": 1,
        "so_ngay_toi_da": 20,
        "dieu_kien_chi_dinh": "Hạn chế vận động sau tai biến mạch máu não hoặc chấn thương. Bắt buộc đo cơ lực trước điều trị.",
        "icd_phu_hop": "I69, G81, M54, M25"
    }
]


def sync_thu_thuat_bhyt(conn: sqlite3.Connection, procedures: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Sync medical procedures and TCM physical therapies into SQLite database."""
    items = procedures or OFFICIAL_TT13_PROCEDURES
    c = conn.cursor()
    synced_cnt = 0

    for p in items:
        c.execute("""
        INSERT OR REPLACE INTO thu_thuat_bhyt (
            ma_dich_vu, ten_dich_vu, chuyen_khoa, gia_bhyt, dinh_muc_ngay,
            so_ngay_toi_da, dieu_kien_chi_dinh, icd_phu_hop
        ) VALUES (
            :ma_dich_vu, :ten_dich_vu, :chuyen_khoa, :gia_bhyt, :dinh_muc_ngay,
            :so_ngay_toi_da, :dieu_kien_chi_dinh, :icd_phu_hop
        )
        """, p)
        synced_cnt += 1

    conn.commit()
    logger.info(f"Successfully synced {synced_cnt} BHYT TT13/39 procedures into database.")
    return {"status": "SUCCESS", "synced_count": synced_cnt}
