"""
Thuốc Tân Dược BHYT Sync Engine (Thông tư 20/2022/TT-BYT & Quyết định 7603/QĐ-BYT)
Maintains essential pharmaceuticals with hospital tier restrictions, payment conditions, and audit notes.
"""

import os
import json
import logging
import sqlite3
from typing import Dict, Any, List, Optional

logger = logging.getLogger("bhyt.thuoc_sync")

OFFICIAL_TT20_DRUGS: List[Dict[str, Any]] = [
    # --- NHÓM KHÁNG SINH & KHÁNG KHUẨN ---
    {
        "ma_hoat_chat": "01.01",
        "ten_hoat_chat": "Amoxicillin + Acid Clavulanic",
        "nhom_duoc_ly": "Kháng sinh nhóm Penicillin kết hợp ức chế beta-lactamase",
        "duong_dung": "Uống / Tiêm truyền",
        "ham_luong": "500mg/125mg, 875mg/125mg, 1g",
        "hang_bv_duoc_ke": "1,2,3,4",
        "ty_le_thanh_toan": 100,
        "dieu_kien_thanh_toan": "Chỉ định nhiễm khuẩn đường hô hấp, tiết niệu khi nghi ngờ hoặc có bằng chứng kháng amoxicillin đơn thuần.",
        "ghi_chu_xuat_toan": "Xuất toán nếu chỉ định cho viêm họng, cảm cúm thông thường do virus (J00, J06) mà không có bằng chứng bội nhiễm.",
        "yeu_cau_can_lam_sang": "Bạch cầu máu tăng hoặc CRP tăng hoặc hình ảnh viêm trên X-quang phổi/khám lâm sàng mủ."
    },
    {
        "ma_hoat_chat": "01.02",
        "ten_hoat_chat": "Cefixim",
        "nhom_duoc_ly": "Kháng sinh Cephalosporin thế hệ 3",
        "duong_dung": "Uống",
        "ham_luong": "100mg, 200mg",
        "hang_bv_duoc_ke": "1,2,3,4",
        "ty_le_thanh_toan": 100,
        "dieu_kien_thanh_toan": "Nhiễm khuẩn hô hấp dưới, viêm tai giữa, nhiễm khuẩn tiết niệu.",
        "ghi_chu_xuat_toan": "Tuyến 4 (trạm y tế/phòng khám tư) cần có triệu chứng nhiễm trùng sốt hoặc xét nghiệm bạch cầu để bảo vệ chỉ định.",
        "yeu_cau_can_lam_sang": "Công thức máu hoặc triệu chứng sốt >= 38.5C ghi trong hồ sơ."
    },
    {
        "ma_hoat_chat": "01.03",
        "ten_hoat_chat": "Ceftriaxone",
        "nhom_duoc_ly": "Kháng sinh Cephalosporin thế hệ 3 tiêm",
        "duong_dung": "Tiêm bắp / Tiêm truyền tĩnh mạch",
        "ham_luong": "1g, 2g",
        "hang_bv_duoc_ke": "1,2,3",
        "ty_le_thanh_toan": 100,
        "dieu_kien_thanh_toan": "Chỉ định nhiễm khuẩn nặng nội trú hoặc cấp cứu ngoại trú tại Bệnh viện Hạng 1, 2, 3.",
        "ghi_chu_xuat_toan": "Xuất toán 100% nếu kê tại Phòng khám Đa khoa tư nhân hoặc Trạm Y tế (Tuyến 4) trừ trường hợp cấp cứu chuyển viện.",
        "yeu_cau_can_lam_sang": "Chỉ định nội trú hoặc bệnh án cấp cứu có biên bản hội chẩn."
    },
    {
        "ma_hoat_chat": "01.04",
        "ten_hoat_chat": "Levofloxacin",
        "nhom_duoc_ly": "Kháng sinh Fluoroquinolone phổ rộng",
        "duong_dung": "Uống / Tiêm truyền",
        "ham_luong": "500mg, 750mg",
        "hang_bv_duoc_ke": "1,2,3",
        "ty_le_thanh_toan": 100,
        "dieu_kien_thanh_toan": "Viêm phổi mắc phải cộng đồng mức độ trung bình-nặng, nhiễm trùng tiết niệu phức tạp.",
        "ghi_chu_xuat_toan": "Không được dùng làm kháng sinh lựa chọn đầu tay cho nhiễm khuẩn hô hấp nhẹ; tuyến 4 bị xuất toán.",
        "yeu_cau_can_lam_sang": "X-quang ngực thẳng hoặc cấy vi khuẩn."
    },
    {
        "ma_hoat_chat": "01.05",
        "ten_hoat_chat": "Azithromycin",
        "nhom_duoc_ly": "Kháng sinh Macrolide",
        "duong_dung": "Uống",
        "ham_luong": "250mg, 500mg",
        "hang_bv_duoc_ke": "1,2,3,4",
        "ty_le_thanh_toan": 100,
        "dieu_kien_thanh_toan": "Nhiễm khuẩn hô hấp trên/dưới do vi khuẩn không điển hình hoặc bệnh nhân dị ứng beta-lactam.",
        "ghi_chu_xuat_toan": "Kê quá 3-5 ngày trong 1 đợt điều trị thông thường cần ghi nhận giải trình lâm sàng.",
        "yeu_cau_can_lam_sang": ""
    },

    # --- NHÓM GIẢM ĐAU, HẠ SỐT & KHÁNG VIÊM NSAID ---
    {
        "ma_hoat_chat": "02.01",
        "ten_hoat_chat": "Paracetamol",
        "nhom_duoc_ly": "Giảm đau hạ sốt non-opioid",
        "duong_dung": "Uống / Đặt hậu môn / Tiêm truyền",
        "ham_luong": "500mg, 650mg, 1000mg",
        "hang_bv_duoc_ke": "1,2,3,4",
        "ty_le_thanh_toan": 100,
        "dieu_kien_thanh_toan": "Hạ sốt khi thân nhiệt >= 38.5C hoặc giảm đau mức độ nhẹ-vừa.",
        "ghi_chu_xuat_toan": "Xuất toán nếu kê tổng liều vượt quá 4g/ngày ở người lớn hoặc kê trùng hoạt chất giữa các biệt dược (VD: Hapacol + Panadol).",
        "yeu_cau_can_lam_sang": "Chỉ số nhiệt độ hoặc thang điểm đau VAS."
    },
    {
        "ma_hoat_chat": "02.02",
        "ten_hoat_chat": "Meloxicam",
        "nhom_duoc_ly": "Kháng viêm không steroid (NSAID ức chế ưu thế COX-2)",
        "duong_dung": "Uống / Tiêm bắp",
        "ham_luong": "7.5mg, 15mg",
        "hang_bv_duoc_ke": "1,2,3,4",
        "ty_le_thanh_toan": 100,
        "dieu_kien_thanh_toan": "Thoái hóa khớp (M15-M19), viêm khớp dạng thấp (M05-M06), viêm cột sống dính khớp (M45).",
        "ghi_chu_xuat_toan": "Xuất toán nếu kê đồng thời với 1 NSAID khác (kê trùng nhóm NSAID) hoặc kê cho bệnh nhân loét dạ dày tá tràng tiến triển mà không có PPI bảo vệ.",
        "yeu_cau_can_lam_sang": "X-quang khớp hoặc bệnh án đau khớp mạn tính."
    },
    {
        "ma_hoat_chat": "02.03",
        "ten_hoat_chat": "Celecoxib",
        "nhom_duoc_ly": "Kháng viêm NSAID ức chế chọn lọc COX-2",
        "duong_dung": "Uống",
        "ham_luong": "100mg, 200mg",
        "hang_bv_duoc_ke": "1,2,3,4",
        "ty_le_thanh_toan": 100,
        "dieu_kien_thanh_toan": "Bệnh nhân có nguy cơ xuất huyết tiêu hóa cao cần điều trị viêm khớp thoái hóa.",
        "ghi_chu_xuat_toan": "Thận trọng và xuất toán nếu kê đơn cho bệnh nhân suy tim ứ huyết nặng hoặc thiếu máu cơ tim cục bộ rõ.",
        "yeu_cau_can_lam_sang": ""
    },

    # --- NHÓM TIM MẠCH, HUYẾT ÁP & LIPID MÁU ---
    {
        "ma_hoat_chat": "03.01",
        "ten_hoat_chat": "Amlodipine",
        "nhom_duoc_ly": "Chẹn kênh canxi Dihydropyridine",
        "duong_dung": "Uống",
        "ham_luong": "5mg, 10mg",
        "hang_bv_duoc_ke": "1,2,3,4",
        "ty_le_thanh_toan": 100,
        "dieu_kien_thanh_toan": "Tăng huyết áp vô căn (I10), đau thắt ngực ổn định (I20).",
        "ghi_chu_xuat_toan": "Bắt buộc có huyết áp đo thực tế lúc khám >= 140/90 mmHg hoặc ghi nhận tiền sử điều trị liên tục.",
        "yeu_cau_can_lam_sang": "Huyết áp ghi nhận cụ thể trong hồ sơ khám."
    },
    {
        "ma_hoat_chat": "03.02",
        "ten_hoat_chat": "Atorvastatin",
        "nhom_duoc_ly": "Thuốc ức chế HMG-CoA reductase (Statin hạ lipid máu)",
        "duong_dung": "Uống",
        "ham_luong": "10mg, 20mg, 40mg",
        "hang_bv_duoc_ke": "1,2,3,4",
        "ty_le_thanh_toan": 100,
        "dieu_kien_thanh_toan": "Rối loạn chuyển hóa lipoprotein và tình trạng tăng lipid máu khác (E78).",
        "ghi_chu_xuat_toan": "Xuất toán 100% tiền thuốc nếu hồ sơ bệnh án không có xét nghiệm Cholesterol toàn phần, Triglyceride hoặc LDL-C trong vòng 3-6 tháng.",
        "yeu_cau_can_lam_sang": "Xét nghiệm bộ mỡ máu (Lipid panel: Cholesterol/Triglyceride/LDL-C/HDL-C)."
    },
    {
        "ma_hoat_chat": "03.03",
        "ten_hoat_chat": "Losartan",
        "nhom_duoc_ly": "Thuốc đối kháng thụ thể Angiotensin II (ARB)",
        "duong_dung": "Uống",
        "ham_luong": "50mg, 100mg",
        "hang_bv_duoc_ke": "1,2,3,4",
        "ty_le_thanh_toan": 100,
        "dieu_kien_thanh_toan": "Tăng huyết áp (I10), bảo vệ thận ở bệnh nhân đái tháo đường type 2 có protein niệu.",
        "ghi_chu_xuat_toan": "Chống chỉ định phụ nữ có thai (O00-O99).",
        "yeu_cau_can_lam_sang": "Điện giải đồ Kali máu và Creatinine huyết thanh."
    },
    {
        "ma_hoat_chat": "03.04",
        "ten_hoat_chat": "Fenofibrate",
        "nhom_duoc_ly": "Dẫn xuất acid fibric hạ Triglyceride",
        "duong_dung": "Uống",
        "ham_luong": "145mg, 160mg, 200mg, 300mg",
        "hang_bv_duoc_ke": "1,2,3,4",
        "ty_le_thanh_toan": 100,
        "dieu_kien_thanh_toan": "Tăng Triglyceride máu đơn thuần hoặc hỗn hợp (E78.1, E78.2) khi Triglyceride >= 5.6 mmol/L.",
        "ghi_chu_xuat_toan": "Xuất toán nếu kê khi Triglyceride bình thường mà chỉ tăng Cholesterol đơn thuần (E78.0).",
        "yeu_cau_can_lam_sang": "Chỉ số Triglyceride máu."
    },

    # --- NHÓM ĐÁI THÁO ĐƯỜNG ---
    {
        "ma_hoat_chat": "04.01",
        "ten_hoat_chat": "Metformin",
        "nhom_duoc_ly": "Biguanide hạ đường huyết",
        "duong_dung": "Uống",
        "ham_luong": "500mg, 850mg, 1000mg",
        "hang_bv_duoc_ke": "1,2,3,4",
        "ty_le_thanh_toan": 100,
        "dieu_kien_thanh_toan": "Đái tháo đường type 2 (E11), đặc biệt ở bệnh nhân thừa cân béo phì.",
        "ghi_chu_xuat_toan": "Xuất toán nếu bệnh án không có xét nghiệm đường huyết (Glucose đói hoặc HbA1c) hoặc chỉ định cho bệnh nhân suy thận nặng eGFR < 30.",
        "yeu_cau_can_lam_sang": "Glucose huyết hoặc HbA1c và Creatinine máu/eGFR."
    },
    {
        "ma_hoat_chat": "04.02",
        "ten_hoat_chat": "Gliclazide",
        "nhom_duoc_ly": "Sulfonylurea thế hệ 2",
        "duong_dung": "Uống",
        "ham_luong": "30mg MR, 60mg MR, 80mg",
        "hang_bv_duoc_ke": "1,2,3,4",
        "ty_le_thanh_toan": 100,
        "dieu_kien_thanh_toan": "Đái tháo đường không phụ thuộc insulin type 2 khi chế độ ăn và vận động không đủ kiểm soát.",
        "ghi_chu_xuat_toan": "Cần hướng dẫn và cảnh báo hạ đường huyết trong đơn.",
        "yeu_cau_can_lam_sang": "Glucose máu."
    },

    # --- NHÓM TIÊU HÓA, DẠ DÀY & GAN MẬT ---
    {
        "ma_hoat_chat": "05.01",
        "ten_hoat_chat": "Esomeprazole",
        "nhom_duoc_ly": "Thuốc ức chế bơm proton (PPI)",
        "duong_dung": "Uống / Tiêm truyền",
        "ham_luong": "20mg, 40mg",
        "hang_bv_duoc_ke": "1,2,3,4",
        "ty_le_thanh_toan": 100,
        "dieu_kien_thanh_toan": "Trào ngược dạ dày - thực quản (K21), loét dạ dày tá tràng (K25, K26), dự phòng loét do NSAID.",
        "ghi_chu_xuat_toan": "Thời gian điều trị đợt ngoại trú tối đa 4 - 8 tuần; nếu kê kéo dài liên tục > 3 tháng bắt buộc phải có kết quả nội soi dạ dày thực quản.",
        "yeu_cau_can_lam_sang": "Nội soi dạ dày hoặc chẩn đoán lâm sàng trào ngược rõ."
    },
    {
        "ma_hoat_chat": "05.02",
        "ten_hoat_chat": "Phosphalugel (Aluminium phosphate)",
        "nhom_duoc_ly": "Thuốc kháng acid (Antacid)",
        "duong_dung": "Uống (dạng gel gói)",
        "ham_luong": "20g",
        "hang_bv_duoc_ke": "1,2,3,4",
        "ty_le_thanh_toan": 100,
        "dieu_kien_thanh_toan": "Giảm triệu chứng ợ chua, nóng rát thượng vị, viêm dạ dày cấp.",
        "ghi_chu_xuat_toan": "Không kê quá 14 ngày/đơn mà không kèm thuốc điều trị căn nguyên.",
        "yeu_cau_can_lam_sang": ""
    },

    # --- NHÓM CHỐNG ĐÔNG & KHÁNG TIỂU CẦU ---
    {
        "ma_hoat_chat": "06.01",
        "ten_hoat_chat": "Aspirin (Acid acetylsalicylic)",
        "nhom_duoc_ly": "Thuốc ức chế kết tập tiểu cầu",
        "duong_dung": "Uống",
        "ham_luong": "81mg, 100mg",
        "hang_bv_duoc_ke": "1,2,3,4",
        "ty_le_thanh_toan": 100,
        "dieu_kien_thanh_toan": "Dự phòng thứ phát nhồi máu cơ tim, đột quỵ thiếu máu cục bộ, bệnh tim thiếu máu cục bộ mạn.",
        "ghi_chu_xuat_toan": "Cấm phối hợp đồng thời với các vị thuốc hoạt huyết mạnh (Đan sâm, Đương quy) liều cao mà không có theo dõi đông máu.",
        "yeu_cau_can_lam_sang": "Tiền sử tim mạch / Điện tâm đồ hoặc xét nghiệm tiểu cầu."
    },
    {
        "ma_hoat_chat": "06.02",
        "ten_hoat_chat": "Clopidogrel",
        "nhom_duoc_ly": "Kháng kết tập tiểu cầu nhóm Thienopyridine",
        "duong_dung": "Uống",
        "ham_luong": "75mg",
        "hang_bv_duoc_ke": "1,2,3",
        "ty_le_thanh_toan": 100,
        "dieu_kien_thanh_toan": "Dự phòng biến cố huyết khối sau đặt stent mạch vành hoặc dị ứng với Aspirin.",
        "ghi_chu_xuat_toan": "Tuyến 4 (phòng khám tư) kê đơn đơn độc không có giấy chuyển tuyến hoặc chỉ định của chuyên khoa tim mạch sẽ bị từ chối.",
        "yeu_cau_can_lam_sang": "Hồ sơ can thiệp mạch vành hoặc chỉ định chuyển viện."
    }
]


def sync_thuoc_bhyt(conn: sqlite3.Connection, drugs: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Sync Western medicines list into SQLite database."""
    items = drugs or OFFICIAL_TT20_DRUGS
    c = conn.cursor()
    synced_cnt = 0

    for d in items:
        c.execute("""
        INSERT OR REPLACE INTO thuoc_bhyt (
            ma_hoat_chat, ten_hoat_chat, nhom_duoc_ly, duong_dung, ham_luong,
            hang_bv_duoc_ke, ty_le_thanh_toan, dieu_kien_thanh_toan, ghi_chu_xuat_toan, yeu_cau_can_lam_sang
        ) VALUES (
            :ma_hoat_chat, :ten_hoat_chat, :nhom_duoc_ly, :duong_dung, :ham_luong,
            :hang_bv_duoc_ke, :ty_le_thanh_toan, :dieu_kien_thanh_toan, :ghi_chu_xuat_toan, :yeu_cau_can_lam_sang
        )
        """, d)
        synced_cnt += 1

    conn.commit()
    logger.info(f"Successfully synced {synced_cnt} BHYT TT20 drugs into database.")
    return {"status": "SUCCESS", "synced_count": synced_cnt}
