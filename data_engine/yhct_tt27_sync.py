"""
Danh mục Thuốc, Vị thuốc YHCT & Bảng Ánh xạ Chứng trạng YHCT <-> ICD-10
Căn cứ Thông tư 27/2020/TT-BYT & Quyết định 4443/QĐ-BYT của Bộ Y tế.
"""

import os
import json
import logging
import sqlite3
from typing import Dict, Any, List, Optional

logger = logging.getLogger("bhyt.yhct_sync")

OFFICIAL_TT27_HERBS: List[Dict[str, Any]] = [
    {
        "ma_vi_thuoc": "YHCT.01",
        "ten_vi_thuoc": "Đan sâm (Radix Salviae miltiorrhizae)",
        "ten_khoa_hoc": "Salvia miltiorrhiza Bunge",
        "bo_phan_dung": "Rễ và thân rễ phơi khô",
        "tinh_vi_quy_kinh": "Đắng, hơi hàn. Vào kinh Tâm, Can",
        "cong_dung": "Hoạt huyết hóa ứ, thông kinh chỉ thống, thanh tâm trừ phiền",
        "chong_chi_dinh": "Phụ nữ có thai, người đang có hội chứng xuất huyết",
        "hang_bv_duoc_ke": "1,2,3,4",
        "ty_le_thanh_toan": 100,
        "tuong_tac_tay_y": "Tương tác làm tăng nguy cơ xuất huyết nghiêm trọng nếu phối hợp Aspirin, Clopidogrel, Warfarin, Heparin."
    },
    {
        "ma_vi_thuoc": "YHCT.02",
        "ten_vi_thuoc": "Đương quy (Radix Angelicae sinensis)",
        "ten_khoa_hoc": "Angelica sinensis (Oliv.) Diels",
        "bo_phan_dung": "Rễ củ",
        "tinh_vi_quy_kinh": "Ngọt, cay, ấm. Vào kinh Tâm, Can, Tỳ",
        "cong_dung": "Bổ huyết hoạt huyết, nhuận táo hoạt trường, điều kinh chỉ thống",
        "chong_chi_dinh": "Người tỳ hư đại tiện lỏng, rối loạn đông máu",
        "hang_bv_duoc_ke": "1,2,3,4",
        "ty_le_thanh_toan": 100,
        "tuong_tac_tay_y": "Chứa coumarin tự nhiên làm tăng tác dụng chống đông của thuốc kháng đông Tây y."
    },
    {
        "ma_vi_thuoc": "YHCT.03",
        "ten_vi_thuoc": "Cam thảo (Radix Glycyrrhizae)",
        "ten_khoa_hoc": "Glycyrrhiza uralensis Fisch",
        "bo_phan_dung": "Rễ và thân rễ",
        "tinh_vi_quy_kinh": "Ngọt, tính bình. Vào 12 kinh lạc",
        "cong_dung": "Bổ tỳ ích khí, thanh nhiệt giải độc, nhuận phế chỉ ho, điều hòa các vị thuốc",
        "chong_chi_dinh": "Người bị phù nề, tăng huyết áp nặng, suy tim sung huyết",
        "hang_bv_duoc_ke": "1,2,3,4",
        "ty_le_thanh_toan": 100,
        "tuong_tac_tay_y": "Chứa Glycyrrhizin gây giữ muối nước (Na+) và tăng đào thải Kali (K+), triệt tiêu tác dụng thuốc hạ áp và gây hạ Kali máu nặng khi dùng chung thuốc lợi tiểu thiazide hoặc furosemide."
    },
    {
        "ma_vi_thuoc": "YHCT.04",
        "ten_vi_thuoc": "Bạch thược (Radix Paeoniae lactiflorae)",
        "ten_khoa_hoc": "Paeonia lactiflora Pall",
        "bo_phan_dung": "Rễ đã gọt vỏ, luộc chín sấy khô",
        "tinh_vi_quy_kinh": "Chua đắng, hơi hàn. Vào kinh Can, Tỳ",
        "cong_dung": "Dưỡng huyết liễm âm, nhu can chỉ thống, bình can tiềm dương",
        "chong_chi_dinh": "Người tỳ vị hư hàn có tiêu chảy",
        "hang_bv_duoc_ke": "1,2,3,4",
        "ty_le_thanh_toan": 100,
        "tuong_tac_tay_y": "Tương tác an toàn; phối hợp hiệp đồng giảm co thắt cơ vân và đau bụng."
    },
    {
        "ma_vi_thuoc": "YHCT.05",
        "ten_vi_thuoc": "Hoàng kỳ (Radix Astragali)",
        "ten_khoa_hoc": "Astragalus membranaceus (Fisch.) Bunge",
        "bo_phan_dung": "Rễ củ",
        "tinh_vi_quy_kinh": "Ngọt, hơi ấm. Vào kinh Tỳ, Phế",
        "cong_dung": "Bổ khí thăng dương, cố biểu chỉ hãn, lợi niệu tiêu thũng, sinh cơ",
        "chong_chi_dinh": "Hội chứng thực chứng, âm hư hỏa vượng, sốt cao",
        "hang_bv_duoc_ke": "1,2,3,4",
        "ty_le_thanh_toan": 100,
        "tuong_tac_tay_y": "Kích thích miễn dịch tế bào, thận trọng và giảm liều khi bệnh nhân dùng thuốc ức chế miễn dịch (Corticosteroid, Cyclosporine, Tacrolimus)."
    },
    {
        "ma_vi_thuoc": "YHCT.06",
        "ten_vi_thuoc": "Ma hoàng (Herba Ephedrae)",
        "ten_khoa_hoc": "Ephedra sinica Stapf",
        "bo_phan_dung": "Phần thân trên mặt đất",
        "tinh_vi_quy_kinh": "Cay, hơi đắng, ấm. Vào kinh Phế, Bàng quang",
        "cong_dung": "Phát hãn giải biểu, tuyên phế bình suyễn, lợi thủy tiêu thũng",
        "chong_chi_dinh": "Tăng huyết áp nặng, đau thắt ngực, mất ngủ mạn tính, ra mồ hôi nhiều",
        "hang_bv_duoc_ke": "1,2,3",
        "ty_le_thanh_toan": 100,
        "tuong_tac_tay_y": "Chứa alkaloid Ephedrine gây cường giao cảm, co mạch, tăng huyết áp kịch phát và loạn nhịp tim khi phối hợp thuốc chủ vận beta, thuốc ức chế MAO hoặc thuốc chống trầm cảm 3 vòng."
    },
    {
        "ma_vi_thuoc": "YHCT.07",
        "ten_vi_thuoc": "Tam thất (Radix Panacis notoginseng)",
        "ten_khoa_hoc": "Panax notoginseng (Burk.) F.H.Chen",
        "bo_phan_dung": "Rễ củ",
        "tinh_vi_quy_kinh": "Ngọt, hơi đắng, ấm. Vào Can, Vị",
        "cong_dung": "Hóa ứ chỉ huyết, hoạt huyết định thống, bổ khí huyết sau xuất huyết",
        "chong_chi_dinh": "Phụ nữ có thai, người huyết nhiệt chảy máu",
        "hang_bv_duoc_ke": "1,2,3,4",
        "ty_le_thanh_toan": 100,
        "tuong_tac_tay_y": "Nguy cơ chảy máu tăng nếu dùng cùng lúc thuốc chống huyết khối hoặc thuốc NSAID liều cao."
    },
    {
        "ma_vi_thuoc": "YHCT.08",
        "ten_vi_thuoc": "Nhân sâm (Radix Ginseng)",
        "ten_khoa_hoc": "Panax ginseng C.A.Mey",
        "bo_phan_dung": "Rễ củ",
        "tinh_vi_quy_kinh": "Ngọt, hơi đắng, hơi ấm. Vào Tỳ, Phế, Tâm",
        "cong_dung": "Đại bổ nguyên khí, phục mạch cố thoát, bổ tỳ ích phế, sinh tân an thần",
        "chong_chi_dinh": "Huyết áp cao cấp tính, đầy bụng thực tích, tiêu chảy cấp",
        "hang_bv_duoc_ke": "1,2,3",
        "ty_le_thanh_toan": 70,
        "tuong_tac_tay_y": "Có thể làm giảm hiệu lực chống đông của Warfarin và làm tụt đường huyết quá mức khi dùng cùng Insulin/Sulfonylurea."
    },
    {
        "ma_vi_thuoc": "YHCT.09",
        "ten_vi_thuoc": "Xuyên khung (Rhizoma Ligustici chuanxiong)",
        "ten_khoa_hoc": "Ligusticum chuanxiong Hort",
        "bo_phan_dung": "Thân rễ",
        "tinh_vi_quy_kinh": "Cay, ấm. Vào Can, Đởm, Tâm bào",
        "cong_dung": "Hoạt huyết hành khí, khu phong chỉ thống, điều trị đau đầu đau nửa đầu",
        "chong_chi_dinh": "Âm hư hỏa vượng, phụ nữ rong kinh xuất huyết",
        "hang_bv_duoc_ke": "1,2,3,4",
        "ty_le_thanh_toan": 100,
        "tuong_tac_tay_y": "Hiệp đồng tăng tác dụng chống kết tập tiểu cầu của Aspirin và Clopidogrel."
    },
    {
        "ma_vi_thuoc": "YHCT.10",
        "ten_vi_thuoc": "Phụ tử chế (Radix Aconiti lateralis praeparata)",
        "ten_khoa_hoc": "Aconitum carmichaelii Debx",
        "bo_phan_dung": "Rễ củ con đã qua chế biến khử độc",
        "tinh_vi_quy_kinh": "Cay ngọt, đại nhiệt, có độc. Vào kinh Tâm, Thận, Tỳ",
        "cong_dung": "Hồi dương cứu nghịch, bổ hỏa trợ dương, tán hàn chỉ thống",
        "chong_chi_dinh": "Âm hư nội nhiệt, chân nhiệt giả hàn, phụ nữ có thai",
        "hang_bv_duoc_ke": "1,2,3",
        "ty_le_thanh_toan": 100,
        "tuong_tac_tay_y": "Đại độc bảng A, tuyệt đối không dùng cùng thuốc Digoxin hoặc thuốc loạn nhịp tim vì nguy cơ rung thất tử vong."
    }
]

OFFICIAL_YHCT_MAPPINGS: List[Dict[str, Any]] = [
    {
        "ma_benh_yhct": "YHCT.B01",
        "ten_chung_trang": "Tọa cốt phong (Đau dây thần kinh tọa)",
        "bat_cuong_tang_phu": "Biểu lý tương kiêm, Hư thực thác tạp (Khí trệ Huyết ứ + Can Thận hư)",
        "ma_icd10_tuong_duong": "M54.5",
        "ten_benh_tay_y": "Đau thắt lưng lan chân / Thoát vị đĩa đệm",
        "trieu_chung_vong_van_van_thiet": "Đau mỏi thắt lưng lan mông và đùi chân, co rút cơ cạnh sống, Schober (+), Valleix (+), lưỡi tím có điểm ứ huyết, mạch trầm sáp.",
        "phap_tri_de_xuat": "Hoạt huyết hóa ứ, thông kinh hoạt lạc, bổ can thận, chỉ thống."
    },
    {
        "ma_benh_yhct": "YHCT.B02",
        "ten_chung_trang": "Lạc chẩm / Kiên thống (Hội chứng cổ vai cánh tay)",
        "bat_cuong_tang_phu": "Biểu thực hàn (Phong hàn phạm kinh lạc)",
        "ma_icd10_tuong_duong": "M54.2",
        "ten_benh_tay_y": "Đau vùng cổ / Hội chứng cổ vai",
        "trieu_chung_vong_van_van_thiet": "Cổ gáy đau cứng khó quay, co cứng cơ thang và cơ ức đòn chũm, sợ lạnh, mạch phù khẩn.",
        "phap_tri_de_xuat": "Khu phong tán hàn, ôn kinh thông lạc, thư cân chỉ thống."
    },
    {
        "ma_benh_yhct": "YHCT.B03",
        "ten_chung_trang": "Khẩu nhãn oa tà (Liệt dây thần kinh VII ngoại biên)",
        "bat_cuong_tang_phu": "Biểu hàn kinh lạc (Phong hàn trúng lạc)",
        "ma_icd10_tuong_duong": "G51.0",
        "ten_benh_tay_y": "Liệt Bell / Liệt dây thần kinh mặt",
        "trieu_chung_vong_van_van_thiet": "Mắt nhắm không kín (Bell +), méo miệng, nhân trung lệch, mất nếp nhăn trán và rãnh mũi má cùng bên.",
        "phap_tri_de_xuat": "Khu phong tán hàn, hoạt huyết thông lạc."
    },
    {
        "ma_benh_yhct": "YHCT.B04",
        "ten_chung_trang": "Vị quản thống (Viêm loét dạ dày tá tràng)",
        "bat_cuong_tang_phu": "Lý thực nhiệt hoặc Lý hư hàn (Can khí phạm Vị hoặc Tỳ vị hư hàn)",
        "ma_icd10_tuong_duong": "K21.9",
        "ten_benh_tay_y": "Bệnh trào ngược dạ dày - thực quản / Viêm dạ dày",
        "trieu_chung_vong_van_van_thiet": "Đau rát vùng thượng vị, ợ chua, cự án, đau tăng khi stress hoặc đói, rêu lưỡi vàng dầy, mạch huyền.",
        "phap_tri_de_xuat": "Sơ can lý khí, hòa vị chỉ thống."
    },
    {
        "ma_benh_yhct": "YHCT.B05",
        "ten_chung_trang": "Tý chứng (Thoái hóa khớp / Viêm đa khớp)",
        "bat_cuong_tang_phu": "Phong hàn thấp tý kết hợp Can thận hư suy",
        "ma_icd10_tuong_duong": "M17.9",
        "ten_benh_tay_y": "Thoái hóa khớp gối",
        "trieu_chung_vong_van_van_thiet": "Khớp gối lục khục khi vận động, đau tăng khi leo cầu thang hoặc thay đổi thời tiết, hạn chế gập duỗi, cơ lực tứ đầu đùi giảm.",
        "phap_tri_de_xuat": "Khu phong trừ thấp, bổ can thận, hoạt huyết chỉ thống."
    }
]


def sync_thuoc_yhct(conn: sqlite3.Connection, herbs: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Sync TCM herbs into SQLite database."""
    items = herbs or OFFICIAL_TT27_HERBS
    c = conn.cursor()
    synced_cnt = 0

    for h in items:
        c.execute("""
        INSERT OR REPLACE INTO thuoc_yhct (
            ma_vi_thuoc, ten_vi_thuoc, ten_khoa_hoc, bo_phan_dung,
            tinh_vi_quy_kinh, cong_dung, chong_chi_dinh, hang_bv_duoc_ke,
            ty_le_thanh_toan, tuong_tac_tay_y
        ) VALUES (
            :ma_vi_thuoc, :ten_vi_thuoc, :ten_khoa_hoc, :bo_phan_dung,
            :tinh_vi_quy_kinh, :cong_dung, :chong_chi_dinh, :hang_bv_duoc_ke,
            :ty_le_thanh_toan, :tuong_tac_tay_y
        )
        """, h)
        synced_cnt += 1

    conn.commit()
    logger.info(f"Successfully synced {synced_cnt} TCM herbs into database.")
    return {"status": "SUCCESS", "synced_count": synced_cnt}


def sync_yhct_icd10_mapping(conn: sqlite3.Connection, mappings: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Sync TCM clinical syndromes <-> ICD-10 mappings into SQLite database."""
    items = mappings or OFFICIAL_YHCT_MAPPINGS
    c = conn.cursor()
    synced_cnt = 0

    for m in items:
        c.execute("""
        INSERT OR REPLACE INTO yhct_icd10_mapping (
            ma_benh_yhct, ten_chung_trang, bat_cuong_tang_phu, ma_icd10_tuong_duong,
            ten_benh_tay_y, trieu_chung_vong_van_van_thiet, phap_tri_de_xuat
        ) VALUES (
            :ma_benh_yhct, :ten_chung_trang, :bat_cuong_tang_phu, :ma_icd10_tuong_duong,
            :ten_benh_tay_y, :trieu_chung_vong_van_van_thiet, :phap_tri_de_xuat
        )
        """, m)
        synced_cnt += 1

    conn.commit()
    logger.info(f"Successfully synced {synced_cnt} YHCT-ICD10 mappings into database.")
    return {"status": "SUCCESS", "synced_count": synced_cnt}
