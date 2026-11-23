"""
BHYT Clinical Copilot MCP Server
Exposes standardized Model Context Protocol (MCP) tools for:
- Prescription and Procedure Validation (Chống xuất toán BHYT)
- Clinical Justification Generator (Sinh mô tả khám lâm sàng chuẩn BHYT)
- ICD-10 Vietnamese search (15,827 codes)
- Herb-Drug interaction safety checker (YHCT & Tây Y)
- Auto-sync catalog engine (Cập nhật dữ liệu BYT/BHXH mới nhất)
"""

import sys
import os
import json
import sqlite3
from typing import List, Dict, Any, Optional

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "bhyt_catalog.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def search_icd10(keyword: str, limit: int = 10) -> List[Dict[str, Any]]:
    conn = get_db()
    c = conn.cursor()
    kw = f"%{keyword.strip()}%"
    c.execute("""
        SELECT code, code_nodot, name_vn, name_en, chapter_name, block_name, not_allowed_primary, must_use_subcode
        FROM icd10 
        WHERE code LIKE ? OR code_nodot LIKE ? OR name_vn LIKE ? 
        ORDER BY LENGTH(code) ASC, code ASC 
        LIMIT ?
    """, (kw, kw, kw, limit))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

def check_herb_drug_interaction(tcm_herbs: List[str], western_drugs: List[str]) -> List[Dict[str, Any]]:
    conn = get_db()
    c = conn.cursor()
    warnings = []
    
    c.execute("SELECT ten_vi_thuoc, tuong_tac_tay_y FROM thuoc_yhct WHERE tuong_tac_tay_y IS NOT NULL")
    herbs = c.fetchall()
    
    tcm_str = " ".join(tcm_herbs).lower()
    west_str = " ".join(western_drugs).lower()
    
    for h in herbs:
        name = h["ten_vi_thuoc"].split()[0].lower()
        full_name = h["ten_vi_thuoc"].lower()
        if name in tcm_str or any(word in tcm_str for word in full_name.split()[:2]):
            interact = h["tuong_tac_tay_y"]
            if "xuất huyết" in interact or "chống đông" in interact:
                if any(d in west_str for d in ["aspirin", "clopidogrel", "warfarin", "xarelto", "eliquis", "heparin"]):
                    warnings.append({
                        "severity": "HIGH",
                        "herb": h["ten_vi_thuoc"],
                        "drug_risk": "Chống đông / Kháng kết tập tiểu cầu",
                        "detail": interact,
                        "recommendation": "Nguy cơ xuất huyết nội tạng cao. Tạm dừng vị thuốc này hoặc giảm liều và theo dõi thời gian đông máu (PT/INR)."
                    })
            if "huyết áp" in interact or "lợi tiểu" in interact:
                if any(d in west_str for d in ["amlodipine", "losartan", "enalapril", "furosemide", "hydrochlorothiazide"]):
                    warnings.append({
                        "severity": "HIGH",
                        "herb": h["ten_vi_thuoc"],
                        "drug_risk": "Hạ Kali máu / Triệt tiêu tác dụng hạ áp",
                        "detail": interact,
                        "recommendation": "Cam thảo làm tăng giữ muối nước và đào thải Kali. Thận trọng đặc biệt ở bệnh nhân tăng huyết áp kháng trị."
                    })
    conn.close()
    return warnings

def validate_prescription(
    icd_code: str, 
    drugs: List[str], 
    hospital_level: str = "4", # "4" = Phòng khám đa khoa tư nhân / Trạm y tế
    procedures: Optional[List[str]] = None,
    lab_tests: Optional[List[str]] = None,
    procedure_days: int = 1
) -> Dict[str, Any]:
    """
    Core BHYT audit engine:
    1. Kiểm tra mã ICD-10 hợp lệ, có bị cấm làm bệnh chính hoặc bắt buộc dùng mã 4 ký tự không.
    2. Kiểm tra thuốc có vượt tuyến phòng khám (hạng 4) không.
    3. Kiểm tra thiếu xét nghiệm cận lâm sàng bắt buộc (VD: Statin thiếu Lipid máu).
    4. Kiểm tra định mức thủ thuật YHCT (Điện châm, Xoa bóp <= 15 ngày/đợt).
    5. Kiểm tra tương tác YHCT và Tây y.
    """
    conn = get_db()
    c = conn.cursor()
    
    icd_code = icd_code.strip().upper()
    c.execute("""
        SELECT code, name_vn, not_allowed_primary, must_use_subcode 
        FROM icd10 
        WHERE code = ? OR code_nodot = ? 
        LIMIT 1
    """, (icd_code, icd_code.replace('.', '')))
    icd_row = c.fetchone()
    
    alerts = []
    
    if not icd_row:
        alerts.append({
            "severity": "HIGH",
            "rule": "INVALID_ICD",
            "title": "Mã ICD-10 không tồn tại trong danh mục Bộ Y tế",
            "detail": f"Mã '{icd_code}' không hợp lệ hoặc thiếu ký tự phụ (subcode). BHYT sẽ từ chối giám định ngay từ cổng tiếp nhận.",
            "remedy": "Tra cứu lại mã ICD-10 chuẩn từ catalog của hệ thống."
        })
    else:
        disease_name = icd_row["name_vn"]
        if icd_row["not_allowed_primary"]:
            alerts.append({
                "severity": "HIGH",
                "rule": "NOT_ALLOWED_PRIMARY_ICD",
                "title": f"Mã ICD-10 '{icd_code}' KHÔNG được phép làm bệnh chính",
                "detail": "Theo quy chế giám định BHYT của Bộ Y tế, mã này là mã triệu chứng hoặc nguyên nhân ngoài, bắt buộc phải có mã bệnh thực thể làm bệnh chính.",
                "remedy": "Chuyển mã này sang chẩn đoán phụ (bệnh kèm theo) và chọn bệnh lý nguyên nhân làm bệnh chính."
            })
        if icd_row["must_use_subcode"]:
            alerts.append({
                "severity": "HIGH",
                "rule": "MUST_USE_SUBCODE",
                "title": f"Mã ICD-10 '{icd_code}' không được dùng vì đã có mã 4 ký tự chi tiết",
                "detail": "Quy định BHYT yêu cầu mã hóa ở mức độ chi tiết cao nhất. Dùng mã chung 3 ký tự sẽ bị xuất toán hoặc đẩy cổng lỗi.",
                "remedy": "Bổ sung vị trí giải phẫu hoặc thể bệnh chi tiết để đạt mã 4 ký tự."
            })
        
    procedures = procedures or []
    lab_tests = lab_tests or []
    
    # Check all drugs in DB
    c.execute("SELECT * FROM thuoc_bhyt")
    db_drugs = c.fetchall()
    
    for drug in drugs:
        d_lower = drug.lower()
        matched_drug = None
        for d in db_drugs:
            if d["ten_hoat_chat"].lower() in d_lower or d_lower in d["ten_hoat_chat"].lower():
                matched_drug = d
                break
                
        if matched_drug:
            allowed_levels = [x.strip() for x in matched_drug["hang_bv_duoc_ke"].split(",")]
            if hospital_level not in allowed_levels:
                alerts.append({
                    "severity": "HIGH",
                    "rule": "HOSPITAL_LEVEL_EXCEEDED",
                    "title": f"Thuốc '{matched_drug['ten_hoat_chat']}' vượt quá tuyến chuyên môn kỹ thuật",
                    "detail": f"Hoạt chất này chỉ được BHYT thanh toán tại Bệnh viện (Tuyến {matched_drug['hang_bv_duoc_ke']}). Tuyến {hospital_level} (phòng khám tư / trạm y tế) kê đơn sẽ bị XUẤT TOÁN 100%.",
                    "remedy": "Chuyển bệnh nhân lên bệnh viện tuyến trên hoặc thay bằng kháng sinh/hoạt chất dạng uống được phân hạng cho tuyến 4."
                })
                
            # Rule 2: Xét nghiệm bắt buộc kèm theo
            if "statin" in d_lower or "atorvastatin" in d_lower:
                if not any("lipid" in t.lower() or "cholesterol" in t.lower() or "triglyceride" in t.lower() for t in lab_tests):
                    alerts.append({
                        "severity": "HIGH",
                        "rule": "MISSING_REQUIRED_LAB",
                        "title": f"Kê đơn thuốc hạ lipid máu ({matched_drug['ten_hoat_chat']}) nhưng thiếu kết quả xét nghiệm",
                        "detail": "Quy chế BHYT bắt buộc phải có kết quả xét nghiệm Cholesterol/Triglyceride/LDL-C trong hồ sơ để chứng minh chỉ định.",
                        "remedy": "Bổ sung chỉ định xét nghiệm bộ mỡ máu hoặc ghi nhận ngày xét nghiệm gần nhất vào phần tóm tắt bệnh án."
                    })

    # Rule 3: Thủ thuật YHCT vượt định mức ngày
    c.execute("SELECT * FROM thu_thuat_bhyt")
    db_procs = c.fetchall()
    for proc in procedures:
        p_lower = proc.lower()
        matched_proc = None
        for p in db_procs:
            if p["ten_dich_vu"].lower() in p_lower or p_lower in p["ten_dich_vu"].lower():
                matched_proc = p
                break
                
        if matched_proc:
            max_days = matched_proc["so_ngay_toi_da"]
            if procedure_days > max_days:
                alerts.append({
                    "severity": "HIGH",
                    "rule": "PROCEDURE_DAYS_EXCEEDED",
                    "title": f"Chỉ định '{matched_proc['ten_dich_vu']}' vượt quá {max_days} ngày trong 1 đợt",
                    "detail": f"Hồ sơ ghi nhận ngày điều trị thứ {procedure_days}. BHXH quy định tối đa {max_days} ngày/đợt ngoại trú đối với thủ thuật này.",
                    "remedy": f"Cho bệnh nhân nghỉ đợt 1 (tối thiểu 5 ngày), ghi nhận đánh giá lại triệu chứng lâm sàng trước khi mở đợt điều trị mới."
                })

    # Rule 4: Tương tác Đông - Tây y
    herb_alerts = check_herb_drug_interaction(procedures + drugs, drugs)
    for ha in herb_alerts:
        alerts.append({
            "severity": ha["severity"],
            "rule": "HERB_DRUG_INTERACTION",
            "title": f"Cảnh báo tương tác dược liệu YHCT: {ha['herb']}",
            "detail": ha["detail"],
            "remedy": ha["recommendation"]
        })

    conn.close()
    
    passed = len([a for a in alerts if a["severity"] == "HIGH"]) == 0
    return {
        "status": "PASS" if passed else "FAIL_RISK",
        "icd_code": icd_code,
        "disease_name": icd_row["name_vn"] if icd_row else "Không xác định",
        "total_alerts": len(alerts),
        "high_risk_count": len([a for a in alerts if a["severity"] == "HIGH"]),
        "alerts": alerts,
        "timestamp": json.dumps({"audit_by": "TaiSanh-BHYT-Copilot-v1"})
    }

def suggest_clinical_note(icd_code: str, procedures: List[str], symptoms: Optional[str] = None) -> Dict[str, Any]:
    """
    Sinh đoạn mô tả lâm sàng hợp thức hóa chỉ định BHYT theo đúng phác đồ Bộ Y tế.
    Giúp bác sĩ không phải gõ tay những triệu chứng bắt buộc để tránh bị xuất toán lý do 'thiếu căn cứ lâm sàng'.
    """
    icd_code = icd_code.strip().upper()
    
    notes = []
    if "M54" in icd_code or "đau lưng" in (symptoms or "").lower():
        notes.append("Lý do khám: Đau mỏi vùng thắt lưng lan xuống mông và đùi, đau tăng khi vận động, cúi ngửa khó khăn.")
        notes.append("Khám thực thể: Cột sống thắt lưng giảm biên độ vận động. Co cứng khối cơ cạnh sống hai bên. Dấu hiệu Schober (+). Ấn các điểm Valleix vùng thắt lưng đau chói (VAS 6/10).")
        notes.append("Chẩn đoán YHCT: Tọa cốt phong thể Khí trệ Huyết ứ kết hợp Can Thận hư.")
        notes.append("Chỉ định phù hợp: Điện châm các huyệt Thận du, Đại trường du, Trật biên, Hoàn khiêu, Ủy trung (tần số 2-5Hz, lưu kim 25 phút). Xoa bóp bấm huyệt giải cơ thắt lưng 20 phút.")
    elif "G51" in icd_code or "liệt mặt" in (symptoms or "").lower():
        notes.append("Lý do khám: Miệng méo sang bên lành, mắt nhắm không kín, ăn uống rơi vãi, xuất hiện sau khi ngủ dậy gặp gió lạnh.")
        notes.append("Khám thực thể: Mất nếp nhăn trán bên tổn thương, rãnh mũi má mờ, dấu hiệu Charles Bell (+). Trương lực cơ mặt giảm.")
        notes.append("Chẩn đoán YHCT: Khẩu nhãn oa tà thể Phong hàn phạm kinh lạc.")
        notes.append("Chỉ định phù hợp: Điện châm Tình minh, Toản trúc, Dương bạch, Địa thương, Giáp xa. Cứu ngải ấm vùng mặt bên liệt.")
    else:
        notes.append(f"Lý do khám: Khám và điều trị theo bệnh cảnh mã ICD-10 {icd_code}.")
        notes.append("Khám lâm sàng: Bệnh nhân tỉnh táo, tiếp xúc tốt. Hội chứng đau khu trú, cơ cứng vùng tổn thương, tầm vận động khớp hạn chế.")
        notes.append("Chỉ định: Kết hợp điều trị bảo tồn nội khoa và vật lý trị liệu / YHCT theo đúng quy trình kỹ thuật Bộ Y tế.")

    return {
        "icd_code": icd_code,
        "suggested_note": "\n".join(notes),
        "justification_for": procedures
    }

# CLI dispatcher if executed directly
if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        print("=== TEST 1: SEARCH ICD-10 ===")
        print(json.dumps(search_icd10("thoái hóa khớp", limit=3), ensure_ascii=False, indent=2))
        
        print("\n=== TEST 2: VALIDATE PRESCRIPTION (Xuất toán Ceftriaxone tuyến 4) ===")
        test_val = validate_prescription(
            icd_code="M54.5",
            drugs=["Ceftriaxone 1g", "Paracetamol 500mg"],
            hospital_level="4",
            procedures=["Điện châm điều trị"],
            procedure_days=18
        )
        print(json.dumps(test_val, ensure_ascii=False, indent=2))
        
        print("\n=== TEST 3: CLINICAL NOTE AUTOFILL ===")
        note = suggest_clinical_note(icd_code="M54.5", procedures=["Điện châm điều trị", "Xoa bóp bấm huyệt"])
        print(json.dumps(note, ensure_ascii=False, indent=2))
