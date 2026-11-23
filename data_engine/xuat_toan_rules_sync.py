"""
BHYT Audit & Xuất Toán Rules Engine Knowledge Base
Comprehensive rule catalog mapping statutory regulations (Thông tư 20, 27, 13, QĐ 7603, QĐ 4443)
into automated audit criteria with concrete clinical remedies for doctors.
"""

import os
import json
import logging
import sqlite3
from typing import Dict, Any, List, Optional

logger = logging.getLogger("bhyt.rules_sync")

OFFICIAL_XUAT_TOAN_RULES: List[Dict[str, Any]] = [
    {
        "rule_code": "RULE_INVALID_ICD",
        "rule_type": "ICD_VALIDATION",
        "title": "Mã ICD-10 không tồn tại trong danh mục Bộ Y tế",
        "description": "Mã ICD-10 bị gõ sai, thiếu ký tự hoặc không nằm trong danh mục chẩn đoán dùng chung ban hành theo Quyết định của Bộ Y tế. Cổng BHYT sẽ chặn ngay từ bước tiếp nhận XML.",
        "severity": "HIGH",
        "legal_basis": "Quyết định 7603/QĐ-BYT & Quyết định 4469/QĐ-BYT",
        "remedy_suggestion": "Tra cứu lại mã ICD-10 chuẩn từ catalog của hệ thống theo đúng phân loại WHO 2019."
    },
    {
        "rule_code": "RULE_MUST_USE_SUBCODE",
        "rule_type": "ICD_SUBCODE_ENFORCEMENT",
        "title": "Mã ICD-10 không được dùng vì đã có mã 4 hoặc 5 ký tự chi tiết hơn",
        "description": "Bác sĩ sử dụng mã nhóm chung 3 ký tự (Ví dụ: M16 - Thoái hóa khớp háng) trong khi Bộ Y tế đã ban hành các mã 4-5 ký tự chi tiết theo vị trí giải phẫu (M16.0, M16.1). BHXH sẽ xuất toán toàn bộ hồ sơ do mã hóa không đầy đủ.",
        "severity": "HIGH",
        "legal_basis": "Cột 25 Danh mục ICD-10 Bộ Y tế & Quy chuẩn XML 130/QĐ-BYT",
        "remedy_suggestion": "Bổ sung vị trí giải phẫu (phải/trái/nguyên phát/thứ phát) để chọn đúng mã 4 hoặc 5 ký tự cụ thể."
    },
    {
        "rule_code": "RULE_NOT_ALLOWED_PRIMARY",
        "rule_type": "ICD_PRIMARY_RESTRICTION",
        "title": "Mã ICD-10 KHÔNG được phép dùng làm bệnh chính",
        "description": "Mã này là mã biểu hiện bệnh (dấu hoa thị *), mã triệu chứng (Chương XVIII) hoặc mã nguyên nhân ngoài (Chương XX). BHYT bắt buộc phải có mã bệnh nguyên căn (dấu chữ thập †) làm bệnh chính.",
        "severity": "HIGH",
        "legal_basis": "Cột 23 Danh mục ICD-10 Bộ Y tế & Hướng dẫn mã hóa WHO",
        "remedy_suggestion": "Chuyển mã này xuống bệnh kèm theo (chẩn đoán phụ) và chọn mã bệnh nguyên căn thực thể làm bệnh chính."
    },
    {
        "rule_code": "RULE_GENDER_MISMATCH",
        "rule_type": "ICD_GENDER_RESTRICTION",
        "title": "Mã ICD-10 không phù hợp với giới tính bệnh nhân",
        "description": "Mã bệnh đặc thù của nữ giới (bệnh phụ khoa, sản khoa N70-N98, O00-O99) chỉ định cho bệnh nhân nam, hoặc mã bệnh tuyến tiền liệt (N40-N51) chỉ định cho bệnh nhân nữ.",
        "severity": "HIGH",
        "legal_basis": "Cột 27 & 28 Danh mục ICD-10 Bộ Y tế",
        "remedy_suggestion": "Kiểm tra lại thông tin hành chính giới tính bệnh nhân hoặc chọn mã bệnh học phù hợp."
    },
    {
        "rule_code": "RULE_HOSPITAL_LEVEL_EXCEEDED",
        "rule_type": "HOSPITAL_LEVEL_RESTRICTION",
        "title": "Kê thuốc/kỹ thuật vượt quá phân tuyến chuyên môn kỹ thuật",
        "description": "Thuốc hoặc kỹ thuật chỉ được thanh toán tại Bệnh viện Hạng 1, 2, 3 nhưng cơ sở khám chữa bệnh Hạng 4 (Phòng khám đa khoa tư nhân, Trạm Y tế) chỉ định ngoại trú.",
        "severity": "HIGH",
        "legal_basis": "Thông tư 20/2022/TT-BYT (Cột phân hạng bệnh viện)",
        "remedy_suggestion": "Chuyển tuyến bệnh nhân lên cơ sở khám chữa bệnh tuyến trên hoặc thay thế bằng hoạt chất tương đương được phân hạng cho tuyến 4."
    },
    {
        "rule_code": "RULE_LIPID_TEST_MISSING",
        "rule_type": "DRUG_LAB_REQUIREMENT",
        "title": "Kê thuốc hạ mỡ máu (Statin/Fibrate) thiếu xét nghiệm Lipid panel",
        "description": "Chẩn đoán Rối loạn lipid máu (E78) và kê Atorvastatin, Rosuvastatin hoặc Fenofibrate nhưng hồ sơ bệnh án không có kết quả xét nghiệm mỡ máu (Cholesterol/Triglyceride/LDL-C) trong vòng 3-6 tháng.",
        "severity": "HIGH",
        "legal_basis": "Quy chế Giám định BHYT & Hướng dẫn điều trị Rối loạn lipid máu Bộ Y tế",
        "remedy_suggestion": "Bổ sung chỉ định xét nghiệm bộ mỡ máu trước khi kê đơn hoặc ghi rõ kết quả xét nghiệm tuyến trước trong tóm tắt hồ sơ."
    },
    {
        "rule_code": "RULE_DIABETES_GLUCOSE_MISSING",
        "rule_type": "DRUG_LAB_REQUIREMENT",
        "title": "Kê thuốc đái tháo đường nhưng thiếu xét nghiệm Glucose máu hoặc HbA1c",
        "description": "Chẩn đoán Đái tháo đường (E11) và kê Metformin, Gliclazide, Insulin nhưng bệnh án không có ghi nhận kết quả đường huyết đói hoặc chỉ số HbA1c định kỳ.",
        "severity": "HIGH",
        "legal_basis": "Hướng dẫn chẩn đoán và điều trị Đái tháo đường type 2 Bộ Y tế",
        "remedy_suggestion": "Cho bệnh nhân làm xét nghiệm đường huyết mao mạch hoặc HbA1c trước khi cấp đơn thuốc."
    },
    {
        "rule_code": "RULE_PROC_LIMIT_EXCEEDED",
        "rule_type": "PROCEDURE_DURATION_LIMIT",
        "title": "Chỉ định thủ thuật YHCT/PHCN vượt quá số ngày cho phép trong một đợt",
        "description": "Điện châm, xoa bóp bấm huyệt hoặc kéo dãn cột sống vượt quá 15 ngày liên tục trong 1 đợt điều trị ngoại trú.",
        "severity": "HIGH",
        "legal_basis": "Thông tư 13/2019/TT-BYT & Quy trình kỹ thuật YHCT Quyết định 5013/QĐ-BYT",
        "remedy_suggestion": "Tạm dừng đợt 1 (tối thiểu 5-7 ngày), ghi nhận đánh giá lại triệu chứng lâm sàng trước khi mở đợt điều trị thứ 2."
    },
    {
        "rule_code": "RULE_DAILY_PROC_OVERQUOTA",
        "rule_type": "PROCEDURE_DAILY_LIMIT",
        "title": "Chỉ định cùng một thủ thuật kỹ thuật quá định mức 1 lần/ngày",
        "description": "Bệnh nhân ngoại trú được chỉ định 2 lần Điện châm hoặc 2 lần Xoa bóp bấm huyệt trong cùng 1 ngày khám.",
        "severity": "HIGH",
        "legal_basis": "Thông tư 39/2018/TT-BYT & Định mức dịch vụ kỹ thuật",
        "remedy_suggestion": "Chỉ thanh toán 1 lần/ngày đối với mỗi loại thủ thuật kỹ thuật cùng chuyên khoa."
    },
    {
        "rule_code": "RULE_HERB_DRUG_BLEED",
        "rule_type": "HERB_DRUG_INTERACTION",
        "title": "Nguy cơ tương tác thuốc gây xuất huyết nghiêm trọng (Đan sâm/Đương quy + Chống đông)",
        "description": "Kê đồng thời vị thuốc Đông y hoạt huyết hóa ứ mạnh với thuốc chống kết tập tiểu cầu (Aspirin, Clopidogrel) hoặc thuốc chống đông (Warfarin, Heparin, DOACs).",
        "severity": "HIGH",
        "legal_basis": "Dược thư Quốc gia Việt Nam & Hướng dẫn an toàn sử dụng thuốc",
        "remedy_suggestion": "Tạm dừng vị thuốc thảo dược hoặc giảm liều và theo dõi chặt chẽ thời gian đông máu (PT/INR, tiểu cầu)."
    },
    {
        "rule_code": "RULE_HERB_DRUG_HYPOKALEMIA",
        "rule_type": "HERB_DRUG_INTERACTION",
        "title": "Nguy cơ hạ Kali máu và mất kiểm soát huyết áp (Cam thảo + Lợi tiểu)",
        "description": "Cam thảo chứa Glycyrrhizin gây giữ Natri và đào thải Kali qua thận, làm triệt tiêu tác dụng hạ áp và gây rối loạn nhịp tim do hạ Kali máu khi dùng chung thuốc lợi tiểu thiazide/furosemide.",
        "severity": "HIGH",
        "legal_basis": "Cảnh báo Dược lý học lâm sàng YHCT",
        "remedy_suggestion": "Bỏ vị cam thảo hoặc dùng liều tối thiểu dưới 4g/ngày ở bệnh nhân tăng huyết áp có dùng thuốc lợi tiểu."
    },
    {
        "rule_code": "RULE_HERB_DRUG_ARRHYTHMIA",
        "rule_type": "HERB_DRUG_INTERACTION",
        "title": "Tương tác độc tính tim mạch chết người (Phụ tử chế + Thuốc trợ tim Digoxin)",
        "description": "Alkaloid trong Phụ tử (Aconitine) hiệp đồng làm tăng độc tính của Digoxin trên cơ tim, nguy cơ gây block nhĩ thất và rung thất đột tử.",
        "severity": "HIGH",
        "legal_basis": "Quy chế Thuốc độc Bảng A Bộ Y tế",
        "remedy_suggestion": "Chống chỉ định tuyệt đối. Không phối hợp Phụ tử với Digoxin hoặc thuốc chống loạn nhịp tim."
    },
    {
        "rule_code": "RULE_DUPLICATE_ACTIVE_INGREDIENT",
        "rule_type": "PRESCRIPTION_SAFETY",
        "title": "Kê trùng hoạt chất giữa các biệt dược trong cùng một đơn thuốc",
        "description": "Đơn thuốc kê đồng thời 2 loại thuốc có tên thương mại khác nhau nhưng chứa cùng một hoạt chất (Ví dụ: Panadol + Hapacol, hoặc Efferalgan + Paracetamol viên).",
        "severity": "HIGH",
        "legal_basis": "Thông tư 52/2017/TT-BYT quy định về kê đơn thuốc",
        "remedy_suggestion": "Xóa bớt 1 biệt dược, chỉ giữ lại 1 loại và chỉnh liều đúng tổng định mức ngày."
    },
    {
        "rule_code": "RULE_DUPLICATE_NSAID",
        "rule_type": "PRESCRIPTION_SAFETY",
        "title": "Kê phối hợp 2 thuốc kháng viêm không steroid (NSAID)",
        "description": "Kê đồng thời Meloxicam và Celecoxib hoặc Diclofenac trong cùng một đợt điều trị. Việc phối hợp 2 NSAID không làm tăng hiệu quả giảm đau mà làm tăng gấp 4 lần nguy cơ loét thủng dạ dày xuất huyết.",
        "severity": "HIGH",
        "legal_basis": "Hướng dẫn điều trị bệnh cơ xương khớp Bộ Y tế",
        "remedy_suggestion": "Chỉ giữ lại 1 loại NSAID phù hợp với cơ địa bệnh nhân."
    },
    {
        "rule_code": "RULE_PPI_PROLONGED_WITHOUT_ENDOSCOPY",
        "rule_type": "DRUG_INDICATIONS",
        "title": "Kê đơn thuốc ức chế bơm proton (PPI) kéo dài > 8 tuần không có nội soi",
        "description": "Điều trị trào ngược dạ dày thực quản (K21) hoặc viêm dạ dày bằng Esomeprazole/Omeprazole liên tục quá 2 tháng ngoại trú mà không có phiếu kết quả nội soi dạ dày thực quản.",
        "severity": "MEDIUM",
        "legal_basis": "Hướng dẫn chẩn đoán và điều trị bệnh Tiêu hóa Bộ Y tế",
        "remedy_suggestion": "Chỉ định nội soi dạ dày thực quản để xác định tổn thương viêm loét trước khi tiếp tục duy trì PPI."
    },
    {
        "rule_code": "RULE_ANTIBIOTIC_VIRAL_INFECTION",
        "rule_type": "ANTIBIOTIC_STEWARDSHIP",
        "title": "Chỉ định kháng sinh cho nhiễm khuẩn hô hấp do virus không bội nhiễm",
        "description": "Chẩn đoán Viêm mũi họng cấp (J00) hoặc Cúm (J10, J11) nhưng kê kháng sinh (Amoxicillin, Cefixim) mà hồ sơ không ghi nhận bằng chứng sốt cao, họng có mủ hoặc bạch cầu tăng.",
        "severity": "HIGH",
        "legal_basis": "Hướng dẫn sử dụng kháng sinh trong bệnh viện Bộ Y tế",
        "remedy_suggestion": "Chuyển sang điều trị triệu chứng (hạ sốt, giảm ho) hoặc bổ sung chẩn đoán bội nhiễm kèm xét nghiệm chứng minh."
    },
    {
        "rule_code": "RULE_MISSING_CLINICAL_JUSTIFICATION",
        "rule_type": "CLINICAL_DOCUMENTATION",
        "title": "Mô tả triệu chứng lâm sàng không tương thích với chỉ định thủ thuật",
        "description": "Chỉ định Điện châm hoặc Kéo nắn cột sống nhưng phần khám thực thể không ghi nhận co cứng cơ, điểm đau Valleix hoặc hạn chế tầm vận động.",
        "severity": "MEDIUM",
        "legal_basis": "Quy chế hồ sơ bệnh án BHYT",
        "remedy_suggestion": "Sử dụng tính năng AI Clinical Note Generator để hoàn thiện mô tả khám thực thể lâm sàng chi tiết theo chuẩn Bộ Y tế."
    },
    {
        "rule_code": "RULE_YHCT_WRONG_DIAGNOSIS",
        "rule_type": "YHCT_NOMENCLATURE",
        "title": "Chỉ định YHCT thiếu mã bệnh hoặc tên chứng trạng theo Quyết định 4443",
        "description": "Thực hiện châm cứu, bấm huyệt hoặc thuốc thang YHCT nhưng phần chẩn đoán chỉ ghi mã Tây y mà không ghi nhận tên bệnh/chứng trạng YHCT tương ứng.",
        "severity": "HIGH",
        "legal_basis": "Quyết định 4443/QĐ-BYT về mã hóa bệnh học Y học cổ truyền",
        "remedy_suggestion": "Bổ sung chẩn đoán YHCT tương đương (Ví dụ: Tọa cốt phong thể Khí trệ Huyết ứ cho mã M54.5)."
    },
    {
        "rule_code": "RULE_PRESCRIPTION_EXCEED_30_DAYS",
        "rule_type": "PRESCRIPTION_LIMIT",
        "title": "Kê đơn thuốc ngoại trú vượt quá thời gian tối đa theo quy định",
        "description": "Kê đơn thuốc bệnh cấp tính vượt quá 7-10 ngày, hoặc kê đơn bệnh mạn tính (huyết áp, tiểu đường) vượt quá 30 ngày cho 1 lần khám ngoại trú.",
        "severity": "HIGH",
        "legal_basis": "Thông tư 52/2017/TT-BYT & Thông tư 18/2018/TT-BYT",
        "remedy_suggestion": "Điều chỉnh số lượng ngày thuốc tối đa không quá 30 ngày cho bệnh mạn tính và hẹn tái khám."
    },
    {
        "rule_code": "RULE_INPATIENT_ONLY_PROCEDURE",
        "rule_type": "PROCEDURE_SETTING",
        "title": "Chỉ định dịch vụ kỹ thuật chỉ được thanh toán trong điều trị nội trú",
        "description": "Các kỹ thuật xâm lấn hoặc phẫu thuật thủ thuật loại 1 chỉ được thanh toán khi bệnh nhân nhập viện nội trú hoặc điều trị ban ngày, không thanh toán cho đơn khám ngoại trú thông thường.",
        "severity": "HIGH",
        "legal_basis": "Thông tư 39/2018/TT-BYT danh mục dịch vụ kỹ thuật",
        "remedy_suggestion": "Chuyển chế độ điều trị nội trú hoặc điều trị ban ngày có lập bệnh án nội trú."
    }
]


def sync_xuat_toan_rules(conn: sqlite3.Connection, rules: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Sync comprehensive xuất toán rules knowledge base into SQLite database."""
    items = rules or OFFICIAL_XUAT_TOAN_RULES
    c = conn.cursor()
    synced_cnt = 0

    for r in items:
        c.execute("""
        INSERT OR REPLACE INTO xuat_toan_rules (
            rule_code, rule_type, title, description, severity, legal_basis, remedy_suggestion
        ) VALUES (
            :rule_code, :rule_type, :title, :description, :severity, :legal_basis, :remedy_suggestion
        )
        """, r)
        synced_cnt += 1

    conn.commit()
    logger.info(f"Successfully synced {synced_cnt} BHYT audit rules into database.")
    return {"status": "SUCCESS", "synced_count": synced_cnt}
