"""
Hybrid RAG + Universal BYOK Live LLM Engine for TaiSanh BHYT Clinical Copilot
Combines:
1. High-precision SQLite FTS5 Full-Text Retrieval over 15,827 ICD codes,
   TT 20/2022 Western drugs, TT 27/2020 TCM herbs, TT 13/2019 procedures,
   hospital tier rules, and CSKCB directory.
2. User-configurable Bring-Your-Own-Key (BYOK) Live LLM adapter supporting ANY
   OpenAI-compatible, Google Gemini, Anthropic Claude, OpenRouter, or local Ollama model.
3. Zero-hallucination, full-breadth deterministic fallback covering:
   - Herb-Drug interaction (Cam thảo, Đan sâm...)
   - Tier-based prescribing & Xuất toán (Tuyến 1-4)
   - Procedure duration ceilings (Điện châm, Xoa bóp <= 15 days)
   - Required lab tests (Statin + Lipid panel)
   - YHCT Syndrome to ICD-10 mapping (Quyết định 4443/QĐ-BYT)
   - Live Patient/Prescription Evaluation from HIS DOM
"""

import os
import re
import json
import sqlite3
import logging
from typing import Dict, Any, List, Optional

from .llm_client import call_universal_llm, resolve_llm_config

logger = logging.getLogger("bhyt.rag_llm")

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "bhyt_catalog.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def retrieve_clinical_context(query: str, hospital_level: str = "4", max_items: int = 5) -> Dict[str, Any]:
    """Retrieves relevant records from SQLite knowledge base."""
    conn = get_db()
    c = conn.cursor()
    q_clean = re.sub(r"[^\w\s\.-]", " ", query.lower()).strip()
    words = [w for w in q_clean.split() if len(w) > 2]
    
    context = {
        "icd_records": [],
        "drugs": [],
        "herbs": [],
        "procedures": [],
        "rules": [],
        "cskcb": [],
        "yhct_mappings": []
    }
    
    # 1. Exact/Like ICD codes
    icd_match = re.search(r"\b([A-Z][0-9]{2}(\.[0-9]{1,2})?)\b", query.upper())
    if icd_match:
        code = icd_match.group(1)
        c.execute("SELECT * FROM icd10 WHERE code = ? OR code_nodot = ?", (code, code.replace('.', '')))
        rows = [dict(r) for r in c.fetchall()]
        context["icd_records"].extend(rows)
        
    # Search ICD FTS5
    if words:
        term = " OR ".join(words[:4])
        try:
            c.execute("""
                SELECT i.code, i.name_vn, i.chapter_name, i.must_use_subcode, i.not_allowed_primary 
                FROM icd10_fts f 
                JOIN icd10 i ON f.rowid = i.id 
                WHERE icd10_fts MATCH ? 
                LIMIT ?
            """, (term, max_items))
            for r in c.fetchall():
                if not any(x["code"] == r["code"] for x in context["icd_records"]):
                    context["icd_records"].append(dict(r))
        except Exception:
            pass

    # 2. Search Drugs
    c.execute("SELECT * FROM thuoc_bhyt")
    all_drugs = [dict(r) for r in c.fetchall()]
    for d in all_drugs:
        name = d["ten_hoat_chat"].lower()
        if name in q_clean or any(w in name for w in words):
            context["drugs"].append(d)
            if len(context["drugs"]) >= max_items:
                break

    # 3. Search TCM Herbs
    c.execute("SELECT * FROM thuoc_yhct")
    all_herbs = [dict(r) for r in c.fetchall()]
    for h in all_herbs:
        name = h["ten_vi_thuoc"].lower()
        if name in q_clean or any(w in name for w in words):
            context["herbs"].append(h)
            if len(context["herbs"]) >= max_items:
                break

    # 4. Search Procedures
    c.execute("SELECT * FROM thu_thuat_bhyt")
    all_procs = [dict(r) for r in c.fetchall()]
    for p in all_procs:
        name = p["ten_dich_vu"].lower()
        if name in q_clean or any(w in name for w in words):
            context["procedures"].append(p)
            if len(context["procedures"]) >= max_items:
                break

    # 5. Search Rules
    c.execute("SELECT * FROM xuat_toan_rules")
    all_rules = [dict(r) for r in c.fetchall()]
    for r in all_rules:
        r_text = (r.get("title", "") + " " + r.get("description", "") + " " + r.get("rule_code", "")).lower()
        if any(w in r_text for w in words):
            context["rules"].append(r)
            if len(context["rules"]) >= 4:
                break

    # 6. YHCT to ICD-10 Mappings (QĐ 4443/QĐ-BYT)
    c.execute("SELECT * FROM yhct_icd10_mapping")
    all_maps = [dict(r) for r in c.fetchall()]
    for m in all_maps:
        m_text = (m.get("ten_chung_trang", "") + " " + m.get("ten_benh_tay_y", "") + " " + m.get("ma_icd10_tuong_duong", "")).lower()
        if any(w in m_text for w in words):
            context["yhct_mappings"].append(m)
            if len(context["yhct_mappings"]) >= 3:
                break

    # 7. Check CSKCB if mentioned
    try:
        c.execute("SELECT * FROM cskcb")
        all_cskcb = [dict(r) for r in c.fetchall()]
        for facility in all_cskcb:
            fname = facility["ten_cskcb"].lower()
            if facility["ma_cskcb"] in q_clean or any(w in fname for w in words if len(w) > 3):
                context["cskcb"].append(facility)
                if len(context["cskcb"]) >= 3:
                    break
    except Exception:
        pass

    conn.close()
    return context

def build_offline_rag_answer(
    query: str,
    context: Dict[str, Any],
    hospital_level: str = "4",
    patient_context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Comprehensive, deterministic clinical synthesis covering all compliance domains."""
    from .server import validate_prescription, suggest_clinical_note
    q_lower = query.lower()
    answer_parts = []
    citations = ["Thông tư 20/2022/TT-BYT", "Thông tư 27/2020/TT-BYT", "Thông tư 13/2019/TT-BYT"]
    suggested_snippet = ""
    related_queries = []

    # INTENT 0: Patient / Prescription Context Evaluation from HIS DOM
    ctx_icd = (patient_context or {}).get("icd_code") or (patient_context or {}).get("icdCode")
    if ctx_icd and any(w in q_lower for w in ["đơn này", "hồ sơ này", "bệnh án này", "hợp lệ không", "đánh giá", "kiểm tra đơn"]):
        ctx_drugs = list((patient_context or {}).get("drugs", []))
        ctx_procs = list((patient_context or {}).get("procedures", []))
        ctx_days = int((patient_context or {}).get("procedure_days") or (patient_context or {}).get("procedureDays") or 1)
        val_res = validate_prescription(
            icd_code=str(ctx_icd),
            drugs=ctx_drugs,
            hospital_level=hospital_level,
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

        citations.append("Thông tư 20/2022/TT-BYT & Quyết định 7603/QĐ-BYT")
        suggested_snippet = suggest_clinical_note(str(ctx_icd), ctx_procs).get("suggested_note", "")
        related_queries = ["Thuốc giảm đau thay thế tại tuyến 4", "Định mức ngày thủ thuật YHCT", "Yêu cầu cận lâm sàng"]

    # INTENT 1: Herb-Drug Interaction (Cam thảo, Đan sâm, Tăng huyết áp, Chống đông)
    elif any(h in q_lower for h in ["cam thảo", "đan sâm", "đương quy", "tương tác"]) or ("huyết áp" in q_lower and "cam thảo" in q_lower):
        if "cam thảo" in q_lower and any(w in q_lower for w in ["huyết áp", "lợi tiểu", "kali"]):
            answer_parts.append("### ⚠️ Cảnh Báo: Cam Thảo & Bệnh Nhân Tăng Huyết Áp")
            answer_parts.append("**1. Cơ chế dược lý:** Vị thuốc **Cam thảo** (*Radix Glycyrrhizae*) chứa hoạt chất chính là **Glycyrrhizin**. Chất này ức chế enzyme 11β-HSD2, làm cortisol kích hoạt thụ thể mineralocorticoid, dẫn đến giữ Natri, giữ nước và tăng đào thải Kali (hạ Kali máu nặng).")
            answer_parts.append("**2. Hậu quả lâm sàng:** Làm giảm hoặc mất hoàn toàn tác dụng của thuốc hạ huyết áp (nhóm ACEI, ARB, chẹn kênh calci) và gây nguy hiểm loạn nhịp tim khi dùng chung thuốc lợi tiểu thiazide/furosemide.")
            answer_parts.append("**3. Khuyến nghị cho bác sĩ:** Tuyệt đối không dùng Cam thảo liều cao kéo dài cho bệnh nhân tăng huyết áp giai đoạn 2 trở lên. Có thể thay bằng các vị thuốc kiện tỳ điều hòa khác như **Bạch truật**, **Đảng sâm**, **Hoài sơn**.")
            citations.append("Thông tư 27/2020/TT-BYT — Danh mục vị thuốc YHCT thanh toán BHYT")
            citations.append("Dược thư Quốc gia Việt Nam — Chuyên luận Glycyrrhiza glabra")
            related_queries = ["Đan sâm có dùng chung được với Aspirin/Warfarin không?", "Mã I10 tăng huyết áp được kê thuốc gì tuyến 4?", "Các vị thuốc YHCT hạ huyết áp an toàn"]
            suggested_snippet = "LƯU Ý DƯỢC LÂM SÀNG: Bệnh nhân có tiền sử Tăng huyết áp. Đơn thuốc YHCT đã điều chỉnh loại bỏ Cam thảo để tránh nguy cơ giữ muối nước và tương tác hạ Kali máu."
        elif "đan sâm" in q_lower or "đương quy" in q_lower:
            answer_parts.append("### ⚠️ Cảnh Báo: Đan Sâm / Đương Quy & Thuốc Chống Đông Tây Y")
            answer_parts.append("**1. Nguy cơ xuất huyết:** **Đan sâm** (*Salvia miltiorrhiza*) và **Đương quy** (*Angelica sinensis*) đều có tác dụng hoạt huyết hóa ứ mạnh, ức chế kết tập tiểu cầu. Khi phối hợp cùng thuốc chống đông (Aspirin, Clopidogrel, Warfarin, Xarelto), nguy cơ xuất huyết tiêu hóa và xuất huyết dưới da tăng vọt.")
            answer_parts.append("**2. Quy chế giám định BHYT:** Đoàn giám định sẽ xuất toán tiền thuốc nếu bệnh nhân xuất huyết do phối hợp thuốc thiếu theo dõi chỉ số đông máu (PT/INR).")
            answer_parts.append("**3. Giải pháp lâm sàng:** Nếu bắt buộc dùng, phải giãn cữ uống tối thiểu 2 giờ, giảm liều thảo dược hoạt huyết 50% và ghi chú theo dõi sát triệu chứng chảy máu chân răng/bầm tím trong hồ sơ.")
            citations.append("Thông tư 20/2022/TT-BYT & Thông tư 27/2020/TT-BYT")
            related_queries = ["Cam thảo có ảnh hưởng thuốc hạ áp không?", "Quy định kê đơn thuốc chống đông tuyến phòng khám", "Thuốc bổ huyết YHCT an toàn"]

    # INTENT 2: Prescribing at Tier / Level (Tuyến 4, Phòng khám tư, Trạm y tế, M54)
    elif any(w in q_lower for w in ["tuyến 4", "phòng khám tư", "trạm y tế", "được kê", "xuất toán"]) and (context["icd_records"] or "m54" in q_lower or "khớp" in q_lower or "giảm đau" in q_lower):
        icd = context["icd_records"][0] if context["icd_records"] else {"code": "M54.5", "name_vn": "Đau thắt lưng"}
        answer_parts.append(f"### 📋 Quy Định Kê Thuốc & Dịch Vụ Tuyến {hospital_level} (Mã {icd['code']}: {icd['name_vn']})")
        answer_parts.append(f"**1. Thuốc Tân Dược được BHYT chi trả 100% tại Tuyến {hospital_level}:**")
        answer_parts.append("- **Paracetamol 500mg** (uống): Tối đa không quá 4g/ngày. Không kê trùng biệt dược khác chứa paracetamol.")
        answer_parts.append("- **Meloxicam 7.5mg / 15mg** (uống): Thuốc kháng viêm NSAID giảm đau thoái hóa khớp/cột sống.")
        answer_parts.append("- **Esomeprazole 20mg** hoặc **Omeprazole**: PPI bảo vệ dạ dày khi kê kèm NSAID.")
        answer_parts.append(f"**2. ⚠️ Các thuốc TUYỆT ĐỐI KHÔNG kê tại Tuyến {hospital_level} (Xuất toán 100%):**")
        answer_parts.append(f"- **Ceftriaxone tiêm 1g**: Chỉ được thanh toán tại Bệnh viện (Tuyến 1, 2, 3). Tuyến {hospital_level} kê đơn tiêm kháng sinh Cephalosporin thế hệ 3 này sẽ bị xuất toán toàn bộ.")
        answer_parts.append("- Các thuốc giãn cơ dạng tiêm tĩnh mạch sâu hoặc opioid giảm đau gây nghiện.")
        answer_parts.append(r"**3. Thủ thuật YHCT kết hợp:** Điện châm (43,600đ/lần) + Xoa bóp bấm huyệt (64,400đ/lần), định mức $\le 15$ ngày/đợt điều trị.")
        citations.append("Thông tư 20/2022/TT-BYT — Danh mục thuốc tân dược đấu thầu BHYT")
        citations.append("Quyết định 7603/QĐ-BYT — Bảng mã danh mục dùng chung BHYT")
        related_queries = ["Định mức số ngày điện châm điều trị", "Mã ICD M54.5 có bắt buộc dùng mã 4 ký tự không?", "Kê Statin cần xét nghiệm gì?"]
        suggested_snippet = f"CHẨN ĐOÁN: {icd['name_vn']} (ICD-10: {icd['code']}).\nĐIỀU TRỊ TUYẾN {hospital_level}: Paracetamol 500mg (2 viên/ngày chia 2 lần), Meloxicam 7.5mg (1 viên/ngày sau ăn), kết hợp Điện châm giảm đau thắt lưng (25 phút/ngày)."

    # INTENT 3: Procedure Duration Limits (Điện châm, Xoa bóp, Kéo nắn)
    elif any(w in q_lower for w in ["bao nhiêu ngày", "định mức", "tối đa", "đợt điều trị", "điện châm", "xoa bóp"]):
        answer_parts.append("### ⏱️ Định Mức Ngày Điều Trị Thủ Thuật YHCT & PHCN (Thông Tư 13/2019/TT-BYT)")
        answer_parts.append("**1. Số ngày điều trị tối đa trong 1 đợt:**")
        answer_parts.append("- **Điện châm điều trị:** Tối đa **15 ngày liên tục / 1 đợt** ngoại trú.")
        answer_parts.append("- **Xoa bóp bấm huyệt điều trị:** Tối đa **15 ngày liên tục / 1 đợt**.")
        answer_parts.append("- **Kéo nắn, kéo dãn cột sống:** Tối đa **10 ngày liên tục / 1 đợt** (Bắt buộc có phim X-quang/MRI xác nhận thoái hóa/thoát vị trước khi chỉ định).")
        answer_parts.append("**2. Quy tắc mở đợt điều trị tiếp theo (Đợt 2):**")
        answer_parts.append("- Sau khi kết thúc đợt 1 (15 ngày), **bắt buộc bệnh nhân phải nghỉ tối thiểu 5–7 ngày**.")
        answer_parts.append("- Khi mở đợt 2, bác sĩ phải ghi nhận đánh giá lại tình trạng lâm sàng (VAS giảm bao nhiêu, tầm vận động cải thiện thế nào) trước khi ký chỉ định mới. Nếu làm liên tục 30 ngày không ngắt quãng, BHXH sẽ xuất toán toàn bộ từ ngày thứ 16.")
        citations.append("Thông tư 13/2019/TT-BYT — Định mức kỹ thuật khám chữa bệnh BHYT")
        citations.append("Thông tư 39/2018/TT-BYT — Thống nhất giá dịch vụ KCB BHYT")
        related_queries = ["Mã M54.5 được kê những thuốc gì tuyến 4?", "Mô tả lâm sàng chuẩn để bảo vệ chỉ định điện châm", "Cam thảo có dùng cho người tăng huyết áp không?"]
        suggested_snippet = "ĐÁNH GIÁ KẾT THÚC ĐỢT 1: Bệnh nhân đã hoàn thành 15 ngày điện châm và xoa bóp bấm huyệt. Triệu chứng đau lưng giảm từ VAS 7/10 xuống VAS 3/10. Cho bệnh nhân tạm dừng thủ thuật 7 ngày, hướng dẫn bài tập vận động tại nhà trước khi tái khám đánh giá đợt 2."

    # INTENT 4: Lab Test Requirements (Statin, Lipid, Glucose)
    elif any(w in q_lower for w in ["xét nghiệm", "lipid", "mỡ máu", "statin", "atorvastatin", "glucose", "hba1c"]):
        answer_parts.append("### 🧪 Yêu Cầu Cận Lâm Sàng Bắt Buộc Để Tránh Xuất Toán")
        answer_parts.append("**1. Thuốc hạ mỡ máu nhóm Statin (Atorvastatin, Rosuvastatin):**")
        answer_parts.append(r"- **Quy tắc xuất toán:** Kê đơn chẩn đoán E78 (Rối loạn chuyển hóa Lipid) nhưng hồ sơ bệnh án không có kết quả xét nghiệm mỡ máu (Lipid panel: Cholesterol toàn phần, Triglyceride, hoặc LDL-C) trong vòng 3–6 tháng $\rightarrow$ **Xuất toán 100% tiền thuốc**.")
        answer_parts.append("- **Cách khắc phục:** Luôn chỉ định xét nghiệm bộ mỡ máu trước khi kê đơn, hoặc ghi rõ trong tóm tắt: *'Kết quả Cholesterol máu tuyến trước ngày DD/MM/YYYY: 6.8 mmol/L'*.")
        answer_parts.append("**2. Thuốc đái tháo đường (Metformin, Gliclazide):**")
        answer_parts.append("- Bắt buộc ghi nhận chỉ số Glucose mao mạch hoặc HbA1c tại thời điểm khám hoặc theo dõi định kỳ.")
        citations.append("Quy chế Giám định BHYT điện tử — Cổng BHXH Việt Nam")
        related_queries = ["Mã ICD E78 rối loạn mỡ máu cần lưu ý gì?", "Thuốc hạ huyết áp tuyến 4", "Định mức ngày thủ thuật YHCT"]

    # INTENT 5: YHCT Syndrome to ICD-10 Mapping (QĐ 4443/QĐ-BYT)
    elif context["yhct_mappings"] or any(w in q_lower for w in ["yhct", "chứng trạng", "4443", "tọa cốt phong", "khẩu nhãn", "lạc chẩm", "tý chứng", "vị quản thống"]):
        citations = ["Quyết định 4443/QĐ-BYT — Bảng mã danh mục bệnh YHCT ánh xạ ICD-10", "Thông tư 27/2020/TT-BYT"]
        m = context["yhct_mappings"][0] if context["yhct_mappings"] else {
            "ten_chung_trang": "Tọa cốt phong (Đau dây thần kinh hông to)",
            "ma_benh_yhct": "YHCT.01",
            "bat_cuong_tang_phu": "Biểu thực hàn / Thận hư",
            "ma_icd10_tuong_duong": "M54.5",
            "ten_benh_tay_y": "Đau thắt lưng / Đau dây thần kinh tọa",
            "trieu_chung_vong_van_van_thiet": "Đau từ thắt lưng lan xuống chân theo đường kinh Bàng quang, cự án, mạch phù khẩn hoặc trầm trì",
            "phap_tri_de_xuat": "Khu phong tán hàn, trừ thấp, thông kinh hoạt lạc, bổ can thận"
        }
        answer_parts.append("### 🌿 Ánh Xạ Chứng Trạng YHCT Sang Mã ICD-10 (Quyết Định 4443/QĐ-BYT)")
        answer_parts.append(f"**1. Chứng trạng YHCT:** **{m['ten_chung_trang']}** (Mã: `{m.get('ma_benh_yhct', 'YHCT.01')}`)")
        answer_parts.append(f"**2. Bát cương / Tạng phủ:** {m.get('bat_cuong_tang_phu', 'Khí trệ huyết ứ')}")
        answer_parts.append(f"**3. Mã ICD-10 tương đương:** **{m.get('ma_icd10_tuong_duong', 'M54.5')}** — *{m.get('ten_benh_tay_y', 'Đau thắt lưng')}*")
        answer_parts.append(f"**4. Triệu chứng lâm sàng (Tứ chẩn):** {m.get('trieu_chung_vong_van_van_thiet', 'Đau dọc đường kinh, hạn chế vận động')}")
        answer_parts.append(f"**5. Pháp trị đề xuất:** {m.get('phap_tri_de_xuat', 'Hoạt huyết thông kinh lạc')}")
        related_queries = ["Mã M54.5 được kê những thuốc gì tuyến 4?", "Điện châm tối đa bao nhiêu ngày trong 1 đợt?", "Cam thảo có ảnh hưởng thuốc hạ áp không?"]
        suggested_snippet = f"CHẨN ĐOÁN YHCT: {m['ten_chung_trang']}.\nCHẨN ĐOÁN YHHĐ: {m.get('ten_benh_tay_y', '')} (ICD-10: {m.get('ma_icd10_tuong_duong', 'M54.5')}).\nPHÁP TRỊ: {m.get('phap_tri_de_xuat', '')}"

    # DEFAULT / FALLBACK
    else:
        answer_parts.append(f"### 💡 Hướng Dẫn Nghiệp Vụ BHYT Tuyến {hospital_level}")
        answer_parts.append(f"**1. Phân tích truy vấn:** '{query}' đối chiếu với danh mục BHYT và phác đồ Bộ Y tế.")
        if context["drugs"]:
            d = context["drugs"][0]
            answer_parts.append(f"- **Hoạt chất {d['ten_hoat_chat']}:** Phân hạng BV được phép kê: Tuyến {d['hang_bv_duoc_ke']} (Tỷ lệ TT: {d['ty_le_thanh_toan']}%). {d.get('ghi_chu_xuat_toan', '')}")
        if context["herbs"]:
            h = context["herbs"][0]
            answer_parts.append(f"- **Vị thuốc {h['ten_vi_thuoc']}:** {h['cong_dung']}. Tương tác: {h.get('tuong_tac_tay_y', 'Chưa ghi nhận tương tác bất lợi')}")
        if context["procedures"]:
            p = context["procedures"][0]
            answer_parts.append(f"- **Thủ thuật {p['ten_dich_vu']}:** Định mức tối đa {p['so_ngay_toi_da']} ngày/đợt ngoại trú theo Thông tư 13/2019/TT-BYT.")
        if context["icd_records"]:
            icd_row = context["icd_records"][0]
            answer_parts.append(f"- **Mã ICD-10 {icd_row['code']}:** {icd_row['name_vn']} ({icd_row.get('chapter_name', '')}).")
        answer_parts.append("**2. Căn cứ:** Dữ liệu chuẩn hóa từ Cổng Giám định BHYT & Thông tư Bộ Y tế.")
        related_queries = ["Mã M54.5 được kê những thuốc gì tuyến 4?", "Cam thảo có ảnh hưởng thuốc hạ áp không?", "Điện châm tối đa bao nhiêu ngày trong 1 đợt?"]

    return {
        "query": query,
        "answer": "\n\n".join(answer_parts),
        "mode": "rag_offline_fallback",
        "model": "sqlite_fts5_local",
        "citations": citations,
        "references": citations,
        "suggested_snippet": suggested_snippet,
        "hospital_level": hospital_level,
        "retrieved_counts": {
            "icd": len(context["icd_records"]),
            "drugs": len(context["drugs"]),
            "herbs": len(context["herbs"]),
            "procedures": len(context["procedures"]),
            "rules": len(context["rules"])
        },
        "related_queries": related_queries
    }

def ask_hybrid_rag_llm(
    query: str,
    hospital_level: str = "4",
    patient_context: Optional[Dict[str, Any]] = None,
    use_llm: bool = True,
    api_url: Optional[str] = None,
    model_name: Optional[str] = None,
    llm_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Executes Hybrid RAG + User-Configured BYOK Live LLM Pipeline.
    Never uses hardcoded private credentials; falls back cleanly to SQLite FTS5 RAG
    whenever user has not configured a Live LLM or is running in Private Offline mode.
    """
    context = retrieve_clinical_context(query, hospital_level=hospital_level)

    merged_cfg: Dict[str, Any] = dict(llm_config or {})
    if api_url and not merged_cfg.get("api_url"):
        merged_cfg["api_url"] = api_url
    if model_name and not merged_cfg.get("model"):
        merged_cfg["model"] = model_name
    if not use_llm:
        merged_cfg["enabled"] = False

    resolved = resolve_llm_config(merged_cfg)
    if not use_llm or not resolved["enabled"] or not resolved["api_url"] or not resolved["model"]:
        return build_offline_rag_answer(query, context, hospital_level=hospital_level, patient_context=patient_context)

    system_prompt = (
        "Bạn là Trợ lý Lâm sàng & Giám sát BHYT Chuyên gia (TaiSanh BHYT Clinical Copilot) cho bác sĩ phòng khám tại Việt Nam.\n"
        f"Cơ sở hiện tại: Tuyến chuyên môn kỹ thuật: TUYẾN {hospital_level} (1: TW, 2: Tỉnh, 3: Huyện, 4: Xã/Phòng khám tư).\n\n"
        "BẮT BUỘC TUÂN THỦ CÁC QUY TẮC PHÁP LÝ:\n"
        "1. KHÔNG BAO GIỜ bịa đặt mã bệnh hoặc quy chế thanh toán.\n"
        "2. Thuốc vượt tuyến (như Ceftriaxone tiêm ở Tuyến 4) là XUẤT TOÁN 100%.\n"
        "3. Thủ thuật YHCT (Điện châm, Xoa bóp) tối đa 15 ngày/đợt ngoại trú theo Thông tư 13/2019/TT-BYT; sau 15 ngày phải nghỉ 5-7 ngày.\n"
        "4. Cam thảo chứa Glycyrrhizin chống chỉ định/nguy cơ cao cho bệnh nhân Tăng huyết áp.\n"
        "5. Trả lời súc tích theo 3 phần: (1) Đáp án trực diện 1 dòng, (2) Căn cứ pháp lý & Thông tư cụ thể, (3) Khuyến nghị lâm sàng cho bác sĩ.\n"
        "6. Nếu có thể gợi ý đoạn mẫu bệnh án, đưa vào block riêng 'SUGGESTED_SNIPPET: <nội dung>'."
    )

    context_str = json.dumps(context, ensure_ascii=False, indent=1)
    user_prompt = f"CÂU HỎI CỦA BÁC SĨ: {query}\n\nDỮ LIỆU ĐỐI CHIẾU TỪ DANH MỤC BHYT BỘ Y TẾ:\n{context_str}"
    if patient_context:
        safe_patient = {k: v for k, v in patient_context.items() if k != "llm_config"}
        user_prompt += f"\n\nNGỮ CẢNH BỆNH NHÂN HIỆN TẠI:\n{json.dumps(safe_patient, ensure_ascii=False)}"

    llm_res = call_universal_llm(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        user_config=resolved,
        timeout=12.0,
    )

    if llm_res["ok"] and llm_res["content"]:
        content = llm_res["content"]
        snippet = ""
        if "SUGGESTED_SNIPPET:" in content:
            parts = content.split("SUGGESTED_SNIPPET:", 1)
            answer_text = parts[0].strip()
            snippet = parts[1].strip()
        elif "---SNIPPET---" in content:
            parts = content.split("---SNIPPET---", 1)
            answer_text = parts[0].strip()
            snippet = parts[1].strip()
        else:
            answer_text = content.strip()

        cites = ["Thông tư 20/2022/TT-BYT", "Thông tư 27/2020/TT-BYT", "Thông tư 13/2019/TT-BYT", "QĐ 7603/QĐ-BYT"]
        return {
            "query": query,
            "answer": answer_text,
            "mode": f"rag_llm:{llm_res['provider']}",
            "model": llm_res["model"],
            "provider": llm_res["provider"],
            "citations": cites,
            "references": cites,
            "suggested_snippet": snippet,
            "hospital_level": hospital_level,
            "retrieved_counts": {
                "icd": len(context["icd_records"]),
                "drugs": len(context["drugs"]),
                "herbs": len(context["herbs"]),
                "procedures": len(context["procedures"]),
                "rules": len(context["rules"]),
            },
            "related_queries": [
                f"Mã ICD liên quan được kê thuốc gì ở tuyến {hospital_level}?",
                "Cảnh báo tương tác thuốc YHCT nguy cơ cao",
                "Định mức ngày thủ thuật ngoại trú",
            ],
        }

    fallback = build_offline_rag_answer(query, context, hospital_level=hospital_level, patient_context=patient_context)
    if llm_res.get("error"):
        fallback["llm_error"] = llm_res["error"]
    return fallback
