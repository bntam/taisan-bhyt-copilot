"""
BHYT Clinical Copilot MCP Server
Exposes standardized Model Context Protocol (MCP) tools for:
- Prescription and Procedure Validation (Chống xuất toán BHYT)
- Clinical Justification Generator (Sinh mô tả khám lâm sàng chuẩn BHYT)
- ICD-10 Vietnamese search (15,827 codes)
- Herb-Drug interaction safety checker (YHCT & Tây Y)
- Auto-sync catalog engine (Cập nhật dữ liệu BYT/BHXH mới nhất)
- Clinical AI Q&A Copilot (Trợ lý hỏi đáp quy chế BHYT, dược lý & YHCT thời gian thực)
"""

import sys
import os
import re
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
        notes.append("Lý do khám: Đau mỏi vùng thắt lưng lan xuống mông và đùi, đau tăng khi vận động cúi ngửa.")
        notes.append("Khám thực thể: Cột sống thắt lưng giảm biên độ vận động. Co cứng khối cơ cạnh sống hai bên. Dấu hiệu Schober (+) 10/12cm. Nghiệm pháp Lasegue 60 độ. Ấn các điểm Valleix vùng thắt lưng đau chói (VAS 6/10).")
        notes.append("Chẩn đoán YHCT: Tọa cốt phong / Yêu thống - Thể Khí trệ Huyết ứ kết hợp Can Thận hư.")
        notes.append("Chẩn đoán YHHĐ: Thoái hóa cột sống thắt lưng, đau dây thần kinh tọa (ICD-10: M54.5).")
        notes.append("Chỉ định phù hợp: Điện châm các huyệt Thận du, Đại trường du, Trật biên, Hoàn khiêu, Ủy trung (tần số 2-5Hz, lưu kim 25 phút). Xoa bóp bấm huyệt giải cơ thắt lưng 20 phút. Tránh mang vác nặng.")
    elif "G51" in icd_code or "liệt mặt" in (symptoms or "").lower():
        notes.append("Lý do khám: Miệng méo sang bên lành, mắt nhắm không kín, ăn uống rơi vãi sau khi ngủ dậy gặp gió lạnh.")
        notes.append("Khám thực thể: Mất nếp nhăn trán bên tổn thương, rãnh mũi má mờ, nhân trung lệch sang bên lành, dấu hiệu Charles Bell (+). Trương lực cơ mặt giảm.")
        notes.append("Chẩn đoán YHCT: Khẩu nhãn oa tà - Thể Phong hàn phạm kinh lạc.")
        notes.append("Chẩn đoán YHHĐ: Liệt dây thần kinh số VII ngoại biên (Bell's palsy) (ICD-10: G51.0).")
        notes.append("Chỉ định phù hợp: Điện châm Tình minh, Toản trúc, Dương bạch, Địa thương, Giáp xa. Cứu ngải ấm vùng mặt bên liệt. Nhỏ nước muối sinh lý bảo vệ giác mạc.")
    elif "I10" in icd_code or "huyết áp" in (symptoms or "").lower():
        notes.append("Lý do khám: Đau đầu vùng chẩm, chóng mặt từng cơn khi thay đổi tư thế.")
        notes.append("Khám thực thể: Huyết áp đo lúc khám: 150/95 mmHg, Mạch: 78 l/p. Tim T1 T2 đều rõ. Phổi thông khí tốt, không rale.")
        notes.append("Chẩn đoán YHCT: Huyễn vựng - Thể Can hỏa thượng viêm.")
        notes.append("Chẩn đoán YHHĐ: Tăng huyết áp nguyên phát (ICD-10: I10).")
        notes.append("Chỉ định phù hợp: Thuốc hạ áp theo danh mục BHYT tuyến 4, tiết chế muối < 5g/ngày, theo dõi huyết áp nhật ký tại nhà.")
    else:
        notes.append(f"Lý do khám: Khám và điều trị theo bệnh cảnh mã ICD-10 {icd_code}.")
        notes.append("Khám thực thể: Bệnh nhân tỉnh táo, tiếp xúc tốt. Hội chứng đau khu trú, cơ cứng vùng tổn thương, tầm vận động khớp hạn chế.")
        notes.append(f"Chẩn đoán YHHĐ: {icd_code}.")
        notes.append("Chỉ định phù hợp: Kết hợp điều trị bảo tồn nội khoa và vật lý trị liệu / YHCT theo đúng quy trình kỹ thuật Bộ Y tế.")

    return {
        "icd_code": icd_code,
        "suggested_note": "\n".join(notes),
        "justification_for": procedures
    }

def ask_clinical_copilot(query: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Clinical AI Q&A Copilot Engine (RAG over BHYT Catalog & Legal Knowledge Base)
    Answers real-time doctor questions about:
    - Drug prescribing rules by hospital level (Tuyến 1, 2, 3, 4)
    - Herb-Drug interaction risks (Cam thảo, Đan sâm, Đương quy...)
    - Procedure duration limits (Điện châm, Xoa bóp <= 15 days/round)
    - ICD-10 coding compliance & 4-digit subcode requirements
    - Clinical note justifications for HIS EMR
    """
    q_lower = query.lower().strip()
    conn = get_db()
    c = conn.cursor()
    
    level = context.get("hospital_level", "4") if context else "4"
    
    # 1. Check for specific drug queries
    c.execute("SELECT * FROM thuoc_bhyt")
    all_drugs = c.fetchall()
    matched_drugs = [d for d in all_drugs if d["ten_hoat_chat"].lower() in q_lower]
    
    # 2. Check for specific herb queries
    c.execute("SELECT * FROM thuoc_yhct")
    all_herbs = c.fetchall()
    matched_herbs = [h for h in all_herbs if h["ten_vi_thuoc"].split()[0].lower() in q_lower or h["ten_vi_thuoc"].lower() in q_lower]
    
    # 3. Check for procedure queries
    c.execute("SELECT * FROM thu_thuat_bhyt")
    all_procs = c.fetchall()
    matched_procs = [p for p in all_procs if p["ten_dich_vu"].lower() in q_lower or any(w in q_lower for w in ["điện châm", "xoa bóp", "cứu ngải", "thủy châm", "kéo dãn"])]

    # 4. Check for ICD codes in query
    icd_match = re.search(r'\b([A-Z][0-9]{2}(\.[0-9]{1,2})?)\b', query.upper())
    icd_info = None
    if icd_match:
        c.execute("SELECT * FROM icd10 WHERE code = ? OR code_nodot = ?", (icd_match.group(1), icd_match.group(1).replace('.', '')))
        icd_info = c.fetchone()

    # 5. Check for YHCT syndrome mappings (QĐ 4443/QĐ-BYT)
    c.execute("SELECT * FROM yhct_icd10_mapping")
    all_yhct_maps = c.fetchall()
    matched_yhct_maps = [
        m for m in all_yhct_maps 
        if m["ten_chung_trang"].lower().split('(')[0].strip() in q_lower 
        or any(w in q_lower for w in m["ten_chung_trang"].lower().split())
        or (m["ma_icd10_tuong_duong"].lower() in q_lower)
    ]

    conn.close()

    answer_parts = []
    references = []
    suggested_snippet = ""
    related_queries = []

    # INTENT 0: Evaluate Context Prescription / Patient from HIS
    if context and context.get("icd_code") and any(w in q_lower for w in ["đơn này", "hồ sơ này", "bệnh án này", "hợp lệ không", "đánh giá", "kiểm tra đơn"]):
        ctx_icd = str(context.get("icd_code") or "")
        ctx_drugs = list(context.get("drugs", []))
        ctx_procs = list(context.get("procedures", []))
        ctx_days = int(context.get("procedure_days", 1))
        val_res = validate_prescription(
            icd_code=ctx_icd,
            drugs=ctx_drugs,
            hospital_level=level,
            procedures=ctx_procs,
            procedure_days=ctx_days
        )
        answer_parts.append(f"### 📋 Đánh Giá Hồ Sơ Bệnh Án Hiện Tại ({ctx_icd} - {val_res.get('disease_name', '')})")
        if val_res.get("high_risk_count", 0) > 0:
            answer_parts.append(f"⚠️ **CẢNH BÁO NGUY CƠ CAO:** Phát hiện {val_res['high_risk_count']} vi phạm dẫn đến xuất toán 100%!")
            for al in val_res.get("alerts", []):
                if al["severity"] == "HIGH":
                    answer_parts.append(f"- **{al['title']}**: {al['detail']}")
                    if al.get("remedy"):
                        answer_parts.append(f"  👉 *Khắc phục:* {al['remedy']}")
        elif len(val_res.get("alerts", [])) > 0:
            answer_parts.append(f"ℹ️ **LƯU Ý:** Phát hiện {len(val_res['alerts'])} điểm cần bổ sung trong hồ sơ.")
            for al in val_res.get("alerts", []):
                answer_parts.append(f"- {al['title']}: {al['detail']}")
        else:
            answer_parts.append("🟢 **Hồ sơ hợp lệ:** Thuốc và thủ thuật chỉ định hoàn toàn phù hợp với phân tuyến chuyên môn kỹ thuật.")

        references.append("Thông tư 20/2022/TT-BYT & Quyết định 7603/QĐ-BYT")
        suggested_snippet = suggest_clinical_note(ctx_icd, ctx_procs).get("suggested_note", "")
        related_queries = ["Thuốc giảm đau thay thế tại tuyến 4", "Định mức ngày thủ thuật YHCT", "Yêu cầu cận lâm sàng"]

    # INTENT A: Herb-Drug Interaction (Cam thảo, Đan sâm, Tăng huyết áp, Chống đông)
    elif any(h in q_lower for h in ["cam thảo", "đan sâm", "đương quy", "tương tác"]) or ("huyết áp" in q_lower and "cam thảo" in q_lower):
        if "cam thảo" in q_lower and any(w in q_lower for w in ["huyết áp", "lợi tiểu", "kali"]):
            answer_parts.append("### ⚠️ Cảnh Báo: Cam Thảo & Bệnh Nhân Tăng Huyết Áp")
            answer_parts.append("**1. Cơ chế dược lý:** Vị thuốc **Cam thảo** (*Radix Glycyrrhizae*) chứa hoạt chất chính là **Glycyrrhizin**. Chất này ức chế enzyme 11β-HSD2, làm cortisol kích hoạt thụ thể mineralocorticoid, dẫn đến giữ Natri, giữ nước và tăng đào thải Kali (hạ Kali máu nặng).")
            answer_parts.append("**2. Hậu quả lâm sàng:** Làm giảm hoặc mất hoàn toàn tác dụng của thuốc hạ huyết áp (nhóm ACEI, ARB, chẹn kênh calci) và gây nguy hiểm loạn nhịp tim khi dùng chung thuốc lợi tiểu thiazide/furosemide.")
            answer_parts.append("**3. Khuyến nghị cho bác sĩ:** Tuyệt đối không dùng Cam thảo liều cao kéo dài cho bệnh nhân tăng huyết áp giai đoạn 2 trở lên. Có thể thay bằng các vị thuốc kiện tỳ điều hòa khác như **Bạch truật**, **Đảng sâm**, **Hoài sơn**.")
            references.append("Thông tư 27/2020/TT-BYT — Danh mục vị thuốc YHCT thanh toán BHYT")
            references.append("Dược thư Quốc gia Việt Nam — Chuyên luận Glycyrrhiza glabra")
            related_queries = ["Đan sâm có dùng chung được với Aspirin/Warfarin không?", "Mã I10 tăng huyết áp được kê thuốc gì tuyến 4?", "Các vị thuốc YHCT hạ huyết áp an toàn"]
            suggested_snippet = "LƯU Ý DƯỢC LÂM SÀNG: Bệnh nhân có tiền sử Tăng huyết áp. Đơn thuốc YHCT đã điều chỉnh loại bỏ Cam thảo để tránh nguy cơ giữ muối nước và tương tác hạ Kali máu."

        elif "đan sâm" in q_lower or "đương quy" in q_lower:
            answer_parts.append("### ⚠️ Cảnh Báo: Đan Sâm / Đương Quy & Thuốc Chống Đông Tây Y")
            answer_parts.append("**1. Nguy cơ xuất huyết:** **Đan sâm** (*Salvia miltiorrhiza*) và **Đương quy** (*Angelica sinensis*) đều có tác dụng hoạt huyết hóa ứ mạnh, ức chế kết tập tiểu cầu. Khi phối hợp cùng thuốc chống đông (Aspirin, Clopidogrel, Warfarin, Xarelto), nguy cơ xuất huyết tiêu hóa và xuất huyết dưới da tăng vọt.")
            answer_parts.append("**2. Quy chế giám định BHYT:** Đoàn giám định sẽ xuất toán tiền thuốc nếu bệnh nhân xuất huyết do phối hợp thuốc thiếu theo dõi chỉ số đông máu (PT/INR).")
            answer_parts.append("**3. Giải pháp lâm sàng:** Nếu bắt buộc dùng, phải giãn cữ uống tối thiểu 2 giờ, giảm liều thảo dược hoạt huyết 50% và ghi chú theo dõi sát triệu chứng chảy máu chân răng/bầm tím trong hồ sơ.")
            references.append("Thông tư 20/2022/TT-BYT & Thông tư 27/2020/TT-BYT")
            related_queries = ["Cam thảo có ảnh hưởng thuốc hạ áp không?", "Quy định kê đơn thuốc chống đông tuyến phòng khám", "Thuốc bổ huyết YHCT an toàn"]

    # INTENT B: Prescribing at Level 4 (Tuyến 4 / Phòng khám tư / Trạm y tế)
    elif any(w in q_lower for w in ["tuyến 4", "phòng khám tư", "trạm y tế", "được kê", "xuất toán"]) and (icd_info or "m54" in q_lower or "khớp" in q_lower or "giảm đau" in q_lower):
        icd_code_disp = icd_info["code"] if icd_info else "M54.5"
        disease_disp = icd_info["name_vn"] if icd_info else "Đau thắt lưng"
        answer_parts.append(f"### 📋 Quy Định Kê Thuốc & Dịch Vụ Tuyến 4 (Mã {icd_code_disp}: {disease_disp})")
        answer_parts.append("**1. Thuốc Tân Dược được BHYT chi trả 100% tại Tuyến 4:**")
        answer_parts.append("- **Paracetamol 500mg** (uống): Tối đa không quá 4g/ngày. Không kê trùng biệt dược khác chứa paracetamol.")
        answer_parts.append("- **Meloxicam 7.5mg / 15mg** (uống): Thuốc kháng viêm NSAID giảm đau thoái hóa khớp/cột sống.")
        answer_parts.append("- **Esomeprazole 20mg** hoặc **Omeprazole**: PPI bảo vệ dạ dày khi kê kèm NSAID.")
        answer_parts.append("**2. ⚠️ Các thuốc TUYỆT ĐỐI KHÔNG kê tại Tuyến 4 (Xuất toán 100%):**")
        answer_parts.append("- **Ceftriaxone tiêm 1g**: Chỉ được thanh toán tại Bệnh viện (Tuyến 1, 2, 3). Phòng khám tư kê đơn tiêm kháng sinh nhóm Cephalosporin thế hệ 3 này sẽ bị từ chối toàn bộ.")
        answer_parts.append("- Các thuốc giãn cơ dạng tiêm tĩnh mạch sâu hoặc opioid giảm đau gây nghiện.")
        answer_parts.append(r"**3. Thủ thuật YHCT kết hợp:** Điện châm (43,600đ/lần) + Xoa bóp bấm huyệt (64,400đ/lần), định mức $\le 15$ ngày/đợt điều trị.")
        references.append("Thông tư 20/2022/TT-BYT — Danh mục thuốc tân dược đấu thầu BHYT")
        references.append("Quyết định 7603/QĐ-BYT — Bảng mã danh mục dùng chung BHYT")
        related_queries = ["Định mức số ngày điện châm điều trị", "Mã ICD M54.5 có bắt buộc dùng mã 4 ký tự không?", "Kê Statin cần xét nghiệm gì?"]
        suggested_snippet = f"CHẨN ĐOÁN: {disease_disp} (ICD-10: {icd_code_disp}).\nĐIỀU TRỊ TUYẾN 4: Paracetamol 500mg (2 viên/ngày chia 2 lần), Meloxicam 7.5mg (1 viên/ngày sau ăn), kết hợp Điện châm giảm đau thắt lưng (25 phút/ngày)."

    # INTENT C: Procedure Duration Limit (Định mức ngày thủ thuật YHCT)
    elif any(w in q_lower for w in ["bao nhiêu ngày", "định mức", "tối đa", "đợt điều trị", "điện châm", "xoa bóp"]):
        answer_parts.append("### ⏱️ Định Mức Ngày Điều Trị Thủ Thuật YHCT & PHCN (Thông Tư 13/2019/TT-BYT)")
        answer_parts.append("**1. Số ngày điều trị tối đa trong 1 đợt:**")
        answer_parts.append("- **Điện châm điều trị:** Tối đa **15 ngày liên tục / 1 đợt** ngoại trú.")
        answer_parts.append("- **Xoa bóp bấm huyệt điều trị:** Tối đa **15 ngày liên tục / 1 đợt**.")
        answer_parts.append("- **Kéo nắn, kéo dãn cột sống:** Tối đa **10 ngày liên tục / 1 đợt** (Bắt buộc có phim X-quang/MRI xác nhận thoái hóa/thoát vị trước khi chỉ định).")
        answer_parts.append("**2. Quy tắc mở đợt điều trị tiếp theo (Đợt 2):**")
        answer_parts.append("- Sau khi kết thúc đợt 1 (15 ngày), **bắt buộc bệnh nhân phải nghỉ tối thiểu 5–7 ngày**.")
        answer_parts.append("- Khi mở đợt 2, bác sĩ phải ghi nhận đánh giá lại tình trạng lâm sàng (VAS giảm bao nhiêu, tầm vận động cải thiện thế nào) trước khi ký chỉ định mới. Nếu làm liên tục 30 ngày không ngắt quãng, BHXH sẽ xuất toán toàn bộ từ ngày thứ 16.")
        references.append("Thông tư 13/2019/TT-BYT — Định mức kỹ thuật khám chữa bệnh BHYT")
        references.append("Thông tư 39/2018/TT-BYT — Thống nhất giá dịch vụ KCB BHYT")
        related_queries = ["Mã M54.5 được kê những thuốc gì tuyến 4?", "Mô tả lâm sàng chuẩn để bảo vệ chỉ định điện châm", "Cam thảo có dùng cho người tăng huyết áp không?"]
        suggested_snippet = "ĐÁNH GIÁ KẾT THÚC ĐỢT 1: Bệnh nhân đã hoàn thành 15 ngày điện châm và xoa bóp bấm huyệt. Triệu chứng đau lưng giảm từ VAS 7/10 xuống VAS 3/10. Cho bệnh nhân tạm dừng thủ thuật 7 ngày, hướng dẫn bài tập vận động tại nhà trước khi tái khám đánh giá đợt 2."

    # INTENT D: Lab Test Requirements (Statin, Tiểu đường, Viêm họng)
    elif any(w in q_lower for w in ["xét nghiệm", "lipid", "mỡ máu", "statin", "atorvastatin", "glucose", "hba1c"]):
        answer_parts.append("### 🧪 Yêu Cầu Cận Lâm Sàng Bắt Buộc Để Tránh Xuất Toán")
        answer_parts.append("**1. Thuốc hạ mỡ máu nhóm Statin (Atorvastatin, Rosuvastatin):**")
        answer_parts.append(r"- **Quy tắc xuất toán:** Kê đơn chẩn đoán E78 (Rối loạn chuyển hóa Lipid) nhưng hồ sơ bệnh án không có kết quả xét nghiệm mỡ máu (Lipid panel: Cholesterol toàn phần, Triglyceride, hoặc LDL-C) trong vòng 3–6 tháng $\rightarrow$ **Xuất toán 100% tiền thuốc**.")
        answer_parts.append("- **Cách khắc phục:** Luôn chỉ định xét nghiệm bộ mỡ máu trước khi kê đơn, hoặc ghi rõ trong tóm tắt: *'Kết quả Cholesterol máu tuyến trước ngày DD/MM/YYYY: 6.8 mmol/L'*.")
        answer_parts.append("**2. Thuốc đái tháo đường (Metformin, Gliclazide):**")
        answer_parts.append("- Bắt buộc ghi nhận chỉ số Glucose mao mạch hoặc HbA1c tại thời điểm khám hoặc theo dõi định kỳ.")
        references.append("Quy chế Giám định BHYT điện tử — Cổng BHXH Việt Nam")
        related_queries = ["Mã ICD E78 rối loạn mỡ máu cần lưu ý gì?", "Thuốc hạ huyết áp tuyến 4", "Định mức ngày thủ thuật YHCT"]

    # INTENT E: YHCT Syndrome to ICD-10 Mapping (Quyết định 4443/QĐ-BYT)
    elif matched_yhct_maps or any(w in q_lower for w in ["yhct", "chứng trạng", "4443", "tọa cốt phong", "khẩu nhãn", "lạc chẩm", "tý chứng", "vị quản thống"]):
        m = matched_yhct_maps[0] if matched_yhct_maps else all_yhct_maps[0]
        answer_parts.append(f"### 🌿 Ánh Xạ Chứng Trạng YHCT Sang Mã ICD-10 (Quyết Định 4443/QĐ-BYT)")
        answer_parts.append(f"**1. Chứng trạng YHCT:** **{m['ten_chung_trang']}** (Mã: `{m['ma_benh_yhct']}`)")
        answer_parts.append(f"**2. Bát cương / Tạng phủ:** {m['bat_cuong_tang_phu']}")
        answer_parts.append(f"**3. Mã ICD-10 tương đương:** **{m['ma_icd10_tuong_duong']}** — *{m['ten_benh_tay_y']}*")
        answer_parts.append(f"**4. Triệu chứng lâm sàng (Tứ chẩn):** {m['trieu_chung_vong_van_van_thiet']}")
        answer_parts.append(f"**5. Pháp trị đề xuất:** {m['phap_tri_de_xuat']}")
        references.append("Quyết định 4443/QĐ-BYT — Bảng mã danh mục bệnh YHCT ánh xạ ICD-10")
        related_queries = ["Mã M54.5 được kê những thuốc gì tuyến 4?", "Điện châm tối đa bao nhiêu ngày trong 1 đợt?", "Cam thảo có ảnh hưởng thuốc hạ áp không?"]
        suggested_snippet = f"CHẨN ĐOÁN YHCT: {m['ten_chung_trang']}.\\nCHẨN ĐOÁN YHHĐ: {m['ten_benh_tay_y']} (ICD-10: {m['ma_icd10_tuong_duong']}).\\nPHÁP TRỊ: {m['phap_tri_de_xuat']}"

    # DEFAULT / FALLBACK: General search & guidance
    else:
        answer_parts.append(f"### 💡 Hướng Dẫn Nghiệp Vụ BHYT: '{query}'")
        if matched_drugs:
            d = matched_drugs[0]
            answer_parts.append(f"**Về hoạt chất {d['ten_hoat_chat']}:** Tuyến bệnh viện được phép kê: Tuyến {d['hang_bv_duoc_ke']} (Tỷ lệ TT: {d['ty_le_thanh_toan']}%). {d['ghi_chu_xuat_toan']}")
        if matched_herbs:
            h = matched_herbs[0]
            answer_parts.append(f"**Về vị thuốc {h['ten_vi_thuoc']}:** {h['cong_dung']}. Tương tác: {h['tuong_tac_tay_y'] or 'Chưa ghi nhận tương tác bất lợi'}")
        if icd_info:
            answer_parts.append(f"**Về mã ICD-10 {icd_info['code']}:** {icd_info['name_vn']} ({icd_info['chapter_name']}).")
            if icd_info["must_use_subcode"]:
                answer_parts.append("⚠️ Lưu ý: BHYT yêu cầu chọn mã 4 ký tự chi tiết cho nhóm bệnh này.")
        if not (matched_drugs or matched_herbs or icd_info):
            answer_parts.append("Bác sĩ có thể hỏi cụ thể về:")
            answer_parts.append("1. **Danh mục thuốc tuyến 4:** 'Thuốc giảm đau mã M54.5?', 'Kháng sinh hô hấp tuyến 4?'")
            answer_parts.append("2. **Tương tác Đông - Tây y:** 'Cam thảo với thuốc huyết áp?', 'Đan sâm với Aspirin?'")
            answer_parts.append("3. **Định mức kỹ thuật:** 'Điện châm tối đa bao nhiêu ngày?', 'Điều kiện chỉ định kéo dãn cột sống?'")
        references.append("Hệ thống Dữ liệu BHYT & YHCT — Phòng Khám Tài Sanh Copilot Engine")
        related_queries = ["Mã M54.5 được kê những thuốc gì tuyến 4?", "Cam thảo có ảnh hưởng thuốc hạ áp không?", "Điện châm tối đa bao nhiêu ngày trong 1 đợt?"]

    return {
        "query": query,
        "answer": "\n\n".join(answer_parts),
        "suggested_snippet": suggested_snippet,
        "references": references,
        "related_queries": related_queries,
        "timestamp": json.dumps({"source": "TaiSanh-BHYT-Knowledge-RAG-v1"})
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

        print("\n=== TEST 4: CLINICAL Q&A COPILOT CHAT ===")
        chat_res = ask_clinical_copilot("Bệnh nhân tăng huyết áp có dùng được Cam thảo không?")
        print("Q:", chat_res["query"])
        print("A:\n", chat_res["answer"])
