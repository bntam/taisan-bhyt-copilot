"""
Danh mục Cơ sở Khám chữa bệnh BHYT (CSKCB) & Nhận diện Tuyến/Hạng bệnh viện.

- Seed danh mục CSKCB tham chiếu cho cả 4 tuyến (1: Trung ương, 2: Tỉnh/TP,
  3: Quận/Huyện, 4: Xã/Phường/Phòng khám).
- `detect_hospital_tier()` suy ra tuyến (dùng làm `hospital_level` cho audit thuốc
  theo cột hạng bệnh viện TT 20/2022) từ mã CSKCB, URL HIS hoặc tên cơ sở.

LƯU Ý DỮ LIỆU: mã CSKCB trong seed là bộ tham chiếu nội bộ để demo/kiểm thử.
Trước khi dùng giám định thật phải đối chiếu với danh mục CSKCB chính thức do
BHXH Việt Nam công bố (cổng gdbhyt.baohiemxahoi.gov.vn) và nạp lại qua
`sync_cskcb(conn, facilities=...)`.
"""

import re
import sqlite3
import logging
import unicodedata
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger("bhyt.cskcb_sync")

VALID_TIERS = ("1", "2", "3", "4")

CSKCB_SEED: List[Dict[str, Any]] = [
    # ---- Tuyến 1: Trung ương / Hạng đặc biệt - Hạng I ----
    {"ma_cskcb": "01001", "ten_cskcb": "Bệnh viện Bạch Mai", "tuyen": "1", "hang_bv": "Hạng đặc biệt", "tinh": "Hà Nội", "loai_hinh": "Bệnh viện đa khoa trung ương"},
    {"ma_cskcb": "01003", "ten_cskcb": "Bệnh viện Hữu Nghị Việt Đức", "tuyen": "1", "hang_bv": "Hạng đặc biệt", "tinh": "Hà Nội", "loai_hinh": "Bệnh viện ngoại khoa trung ương"},
    {"ma_cskcb": "01007", "ten_cskcb": "Bệnh viện K", "tuyen": "1", "hang_bv": "Hạng đặc biệt", "tinh": "Hà Nội", "loai_hinh": "Bệnh viện chuyên khoa ung bướu trung ương"},
    {"ma_cskcb": "01009", "ten_cskcb": "Bệnh viện Nhi Trung ương", "tuyen": "1", "hang_bv": "Hạng đặc biệt", "tinh": "Hà Nội", "loai_hinh": "Bệnh viện chuyên khoa nhi trung ương"},
    {"ma_cskcb": "01011", "ten_cskcb": "Bệnh viện Y học cổ truyền Trung ương", "tuyen": "1", "hang_bv": "Hạng I", "tinh": "Hà Nội", "loai_hinh": "Bệnh viện y học cổ truyền trung ương"},
    {"ma_cskcb": "79014", "ten_cskcb": "Bệnh viện Chợ Rẫy", "tuyen": "1", "hang_bv": "Hạng đặc biệt", "tinh": "TP. Hồ Chí Minh", "loai_hinh": "Bệnh viện đa khoa trung ương"},
    {"ma_cskcb": "79004", "ten_cskcb": "Bệnh viện Đại học Y Dược TP. Hồ Chí Minh", "tuyen": "1", "hang_bv": "Hạng I", "tinh": "TP. Hồ Chí Minh", "loai_hinh": "Bệnh viện đa khoa trực thuộc Bộ"},
    {"ma_cskcb": "46001", "ten_cskcb": "Bệnh viện Trung ương Huế", "tuyen": "1", "hang_bv": "Hạng đặc biệt", "tinh": "Huế", "loai_hinh": "Bệnh viện đa khoa trung ương"},
    {"ma_cskcb": "48001", "ten_cskcb": "Bệnh viện Đà Nẵng", "tuyen": "1", "hang_bv": "Hạng I", "tinh": "Đà Nẵng", "loai_hinh": "Bệnh viện đa khoa thành phố (tuyến cuối khu vực)"},
    # ---- Tuyến 2: Tỉnh / Thành phố ----
    {"ma_cskcb": "54001", "ten_cskcb": "Bệnh viện Đa khoa Tỉnh Phú Yên", "tuyen": "2", "hang_bv": "Hạng II", "tinh": "Phú Yên", "loai_hinh": "Bệnh viện đa khoa tỉnh"},
    {"ma_cskcb": "54002", "ten_cskcb": "Bệnh viện Sản - Nhi Tỉnh Phú Yên", "tuyen": "2", "hang_bv": "Hạng II", "tinh": "Phú Yên", "loai_hinh": "Bệnh viện chuyên khoa tỉnh"},
    {"ma_cskcb": "54003", "ten_cskcb": "Bệnh viện Y học cổ truyền Tỉnh Phú Yên", "tuyen": "2", "hang_bv": "Hạng II", "tinh": "Phú Yên", "loai_hinh": "Bệnh viện y học cổ truyền tỉnh"},
    {"ma_cskcb": "79001", "ten_cskcb": "Bệnh viện Nhân Dân 115", "tuyen": "2", "hang_bv": "Hạng I", "tinh": "TP. Hồ Chí Minh", "loai_hinh": "Bệnh viện đa khoa thành phố"},
    {"ma_cskcb": "79024", "ten_cskcb": "Bệnh viện Nhân Dân Gia Định", "tuyen": "2", "hang_bv": "Hạng I", "tinh": "TP. Hồ Chí Minh", "loai_hinh": "Bệnh viện đa khoa thành phố"},
    {"ma_cskcb": "01005", "ten_cskcb": "Bệnh viện Đa khoa Xanh Pôn", "tuyen": "2", "hang_bv": "Hạng I", "tinh": "Hà Nội", "loai_hinh": "Bệnh viện đa khoa thành phố"},
    {"ma_cskcb": "56001", "ten_cskcb": "Bệnh viện Đa khoa Tỉnh Khánh Hòa", "tuyen": "2", "hang_bv": "Hạng I", "tinh": "Khánh Hòa", "loai_hinh": "Bệnh viện đa khoa tỉnh"},
    {"ma_cskcb": "52001", "ten_cskcb": "Bệnh viện Đa khoa Tỉnh Bình Định", "tuyen": "2", "hang_bv": "Hạng I", "tinh": "Bình Định", "loai_hinh": "Bệnh viện đa khoa tỉnh"},
    # ---- Tuyến 3: Quận / Huyện / Thị xã ----
    {"ma_cskcb": "54005", "ten_cskcb": "Trung tâm Y tế Thành phố Tuy Hòa", "tuyen": "3", "hang_bv": "Hạng III", "tinh": "Phú Yên", "loai_hinh": "Trung tâm y tế tuyến huyện"},
    {"ma_cskcb": "54006", "ten_cskcb": "Trung tâm Y tế Thị xã Sông Cầu", "tuyen": "3", "hang_bv": "Hạng III", "tinh": "Phú Yên", "loai_hinh": "Trung tâm y tế tuyến huyện"},
    {"ma_cskcb": "54007", "ten_cskcb": "Trung tâm Y tế Huyện Tuy An", "tuyen": "3", "hang_bv": "Hạng III", "tinh": "Phú Yên", "loai_hinh": "Trung tâm y tế tuyến huyện"},
    {"ma_cskcb": "54008", "ten_cskcb": "Trung tâm Y tế Thị xã Đông Hòa", "tuyen": "3", "hang_bv": "Hạng III", "tinh": "Phú Yên", "loai_hinh": "Trung tâm y tế tuyến huyện"},
    {"ma_cskcb": "79030", "ten_cskcb": "Bệnh viện Quận 1", "tuyen": "3", "hang_bv": "Hạng II", "tinh": "TP. Hồ Chí Minh", "loai_hinh": "Bệnh viện quận/huyện"},
    {"ma_cskcb": "01020", "ten_cskcb": "Trung tâm Y tế Quận Đống Đa", "tuyen": "3", "hang_bv": "Hạng III", "tinh": "Hà Nội", "loai_hinh": "Trung tâm y tế tuyến huyện"},
    # ---- Tuyến 4: Xã / Phường / Phòng khám ----
    {"ma_cskcb": "54012", "ten_cskcb": "Phòng khám Y học cổ truyền Tài Sanh", "tuyen": "4", "hang_bv": "Chưa xếp hạng", "tinh": "Phú Yên", "loai_hinh": "Phòng khám chuyên khoa YHCT tư nhân"},
    {"ma_cskcb": "54013", "ten_cskcb": "Trạm Y tế Phường 9, Thành phố Tuy Hòa", "tuyen": "4", "hang_bv": "Chưa xếp hạng", "tinh": "Phú Yên", "loai_hinh": "Trạm y tế xã/phường"},
    {"ma_cskcb": "54014", "ten_cskcb": "Trạm Y tế Phường 7, Thành phố Tuy Hòa", "tuyen": "4", "hang_bv": "Chưa xếp hạng", "tinh": "Phú Yên", "loai_hinh": "Trạm y tế xã/phường"},
    {"ma_cskcb": "54015", "ten_cskcb": "Trạm Y tế Xã Bình Kiến", "tuyen": "4", "hang_bv": "Chưa xếp hạng", "tinh": "Phú Yên", "loai_hinh": "Trạm y tế xã/phường"},
    {"ma_cskcb": "54016", "ten_cskcb": "Phòng khám Đa khoa Tư nhân Hòa Bình Tuy Hòa", "tuyen": "4", "hang_bv": "Chưa xếp hạng", "tinh": "Phú Yên", "loai_hinh": "Phòng khám đa khoa tư nhân"},
    {"ma_cskcb": "79100", "ten_cskcb": "Trạm Y tế Phường Bến Nghé", "tuyen": "4", "hang_bv": "Chưa xếp hạng", "tinh": "TP. Hồ Chí Minh", "loai_hinh": "Trạm y tế xã/phường"},
    {"ma_cskcb": "01100", "ten_cskcb": "Trạm Y tế Phường Láng Thượng", "tuyen": "4", "hang_bv": "Chưa xếp hạng", "tinh": "Hà Nội", "loai_hinh": "Trạm y tế xã/phường"},
]

# Hostname fragments of known HIS/portal domains -> mã CSKCB
DOMAIN_HINTS: Dict[str, str] = {
    "bachmai": "01001",
    "vietduc": "01003",
    "benhvienk": "01007",
    "nhitrunguong": "01009",
    "choray": "79014",
    "umc.edu": "79004",
    "bvdaihoc": "79004",
    "bvtwhue": "46001",
    "dananghospital": "48001",
    "bvdanang": "48001",
    "bvdkphuyen": "54001",
    "benhvien115": "79001",
    "bv115": "79001",
    "bvndgiadinh": "79024",
    "taisanh": "54012",
}

# Keyword heuristics on normalized (no-diacritic, lowercase) facility text.
# Ordered most specific first; the first hit wins.
_TIER_KEYWORDS = [
    ("4", 0.75, ("tram y te", "tyt ", "phong kham", "pk ", "pkdk", "y te xa", "y te phuong")),
    ("1", 0.75, ("trung uong", "benh vien k", "dai hoc y", "hang dac biet", "bach mai", "cho ray", "viet duc")),
    ("3", 0.7, ("trung tam y te", "ttyt", "huyen", "quan ", "thi xa", "bv quan", "benh vien quan")),
    ("2", 0.7, ("tinh", "da khoa tinh", "bvdk tinh", "thanh pho", "san nhi", "y hoc co truyen tinh")),
]

_CODE_PARAM_NAMES = ("ma_cskcb", "macskcb", "cskcb", "ma_cs", "facility", "facility_code", "macs")


def normalize_text(text: Optional[str]) -> str:
    """Lowercase, strip Vietnamese diacritics (including đ) and collapse whitespace."""
    if not text:
        return ""
    t = unicodedata.normalize("NFD", str(text)).replace("đ", "d").replace("Đ", "D")
    t = "".join(ch for ch in t if unicodedata.category(ch) != "Mn").lower()
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return f" {t.strip()} " if t.strip() else ""


def sync_cskcb(conn: sqlite3.Connection, facilities: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Upsert CSKCB facilities (idempotent: ma_cskcb is the primary key)."""
    items = facilities or CSKCB_SEED
    c = conn.cursor()
    synced = 0
    for f in items:
        tier = str(f.get("tuyen", "")).strip()
        if tier not in VALID_TIERS or not f.get("ma_cskcb") or not f.get("ten_cskcb"):
            logger.warning(f"Skipping invalid CSKCB record: {f}")
            continue
        c.execute("""
        INSERT OR REPLACE INTO cskcb (ma_cskcb, ten_cskcb, tuyen, hang_bv, tinh, loai_hinh)
        VALUES (:ma_cskcb, :ten_cskcb, :tuyen, :hang_bv, :tinh, :loai_hinh)
        """, {
            "ma_cskcb": str(f["ma_cskcb"]).strip(),
            "ten_cskcb": f["ten_cskcb"],
            "tuyen": tier,
            "hang_bv": f.get("hang_bv"),
            "tinh": f.get("tinh"),
            "loai_hinh": f.get("loai_hinh"),
        })
        synced += 1
    conn.commit()
    logger.info(f"Successfully synced {synced} CSKCB facilities into database.")
    return {"status": "SUCCESS", "synced_count": synced}


def _load_facilities(conn: Optional[sqlite3.Connection]) -> List[Dict[str, Any]]:
    """Facilities from DB when available, otherwise the built-in seed."""
    if conn is not None:
        try:
            rows = [dict(r) for r in conn.execute("SELECT * FROM cskcb")]
            if rows:
                return rows
        except sqlite3.Error:
            pass
    return [dict(f) for f in CSKCB_SEED]


def _result(level: str, confidence: float, source: str, facility: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "level": level,
        "confidence": round(confidence, 2),
        "source": source,
        "matched_facility": facility,
    }


def _codes_from_url(url: str) -> List[str]:
    try:
        parsed = urlparse(url if "://" in url else f"http://{url}")
    except ValueError:
        return []
    codes: List[str] = []
    for name, values in parse_qs(parsed.query).items():
        if name.lower() in _CODE_PARAM_NAMES:
            codes.extend(v.strip() for v in values)
    codes.extend(re.findall(r"(?<!\d)(\d{5})(?!\d)", parsed.path or ""))
    host = (parsed.hostname or "").lower()
    for fragment, code in DOMAIN_HINTS.items():
        if fragment in host:
            codes.append(code)
    return codes


def _match_by_name(text_norm: str, facilities: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Return the facility whose normalized name is contained in (or contains) the text."""
    best, best_len = None, 0
    for f in facilities:
        name_norm = normalize_text(f["ten_cskcb"]).strip()
        text_core = text_norm.strip()
        partial = len(text_core) >= 0.6 * len(name_norm) and text_core in name_norm
        if name_norm and (name_norm in text_norm or partial):
            if len(name_norm) > best_len:
                best, best_len = f, len(name_norm)
    return best


def detect_hospital_tier(
    facility_text: Optional[str] = None,
    facility_code: Optional[str] = None,
    url: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> Dict[str, Any]:
    """Detect hospital tier ('1'..'4') for BHYT tier-restricted audits.

    Priority: exact mã CSKCB > code/domain inside HIS URL > facility name match >
    keyword heuristics > default '4' (safest: strictest drug list).
    Returns {level, confidence, source, matched_facility}.
    """
    facilities = _load_facilities(conn)
    by_code = {f["ma_cskcb"]: f for f in facilities}

    code = (facility_code or "").strip()
    if code:
        if code in by_code:
            f = by_code[code]
            return _result(f["tuyen"], 0.99, "facility_code", f)
        if re.fullmatch(r"\d{5}", code):
            # Unknown 5-digit code: province prefix gives no tier, fall through to text.
            logger.info(f"Mã CSKCB {code} chưa có trong danh mục, dùng heuristic.")

    if url:
        for c in _codes_from_url(url):
            if c in by_code:
                f = by_code[c]
                return _result(f["tuyen"], 0.9, "url", f)

    text_norm = normalize_text(facility_text)
    if text_norm:
        matched = _match_by_name(text_norm, facilities)
        if matched:
            return _result(matched["tuyen"], 0.9, "facility_name", matched)
        for level, confidence, keywords in _TIER_KEYWORDS:
            if any(f" {kw.strip()} " in text_norm or kw in text_norm for kw in keywords):
                return _result(level, confidence, "keyword_heuristic")

    return _result("4", 0.3, "default")


def lookup_cskcb(ma_cskcb: str, conn: Optional[sqlite3.Connection] = None) -> Optional[Dict[str, Any]]:
    """Find a facility by exact mã CSKCB."""
    code = (ma_cskcb or "").strip()
    for f in _load_facilities(conn):
        if f["ma_cskcb"] == code:
            return f
    return None
