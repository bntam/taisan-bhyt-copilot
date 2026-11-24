"""
External Sources & Pluggable MCP Registry
Allows TaiSanh BHYT Clinical Copilot to connect to:
- Third-party Voice MCPs (e.g. LangCare AI voice scribe)
- Custom Hospital/Clinic HIS & Drug Inventory REST APIs
- External BHYT Regulatory Rule Feeds
"""

import os
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger("bhyt.external_sources")

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
REGISTRY_PATH = os.path.join(DATA_DIR, "external_sources.json")

DEFAULT_SOURCES: List[Dict[str, Any]] = [
    {
        "id": "langcare-mcp",
        "name": "LangCare Clinical Voice Scribe MCP",
        "type": "mcp_client",
        "endpoint": "http://127.0.0.1:8990/mcp",
        "enabled": False,
        "description": "Kết nối voice scribe hội thoại bác sĩ - bệnh nhân qua giao thức MCP, nhận transcript và trích xuất SOAP note.",
        "capabilities": ["voice_to_soap", "transcription", "icd_suggestion"],
        "status": "configured",
        "last_checked": None
    },
    {
        "id": "clinic-inventory-api",
        "name": "Kho Dược Nội Bộ Phòng Khám",
        "type": "rest_api",
        "endpoint": "http://127.0.0.1:8000/api/v1/pharmacy/stock",
        "enabled": False,
        "description": "Tra cứu tồn kho thực tế của dược liệu YHCT và thuốc tân dược để đối chiếu trước khi kê đơn.",
        "capabilities": ["stock_lookup", "batch_expiry"],
        "status": "configured",
        "last_checked": None
    },
    {
        "id": "moh-regulatory-feed",
        "name": "Cổng Dữ Liệu Thông Tư BYT Trực Tuyến",
        "type": "rss_feed",
        "endpoint": "https://moh.gov.vn/api/rss/van-ban-moi",
        "enabled": True,
        "description": "Feed cập nhật tự động các văn bản quy phạm pháp luật và thông tư sửa đổi bổ sung về BHYT.",
        "capabilities": ["circular_updates", "price_changes"],
        "status": "active",
        "last_checked": datetime.now().isoformat()
    }
]

def load_sources() -> List[Dict[str, Any]]:
    if not os.path.exists(REGISTRY_PATH):
        save_sources(DEFAULT_SOURCES)
        return DEFAULT_SOURCES
    try:
        with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("sources", DEFAULT_SOURCES)
    except Exception as e:
        logger.error(f"Error loading external sources registry: {e}")
        return DEFAULT_SOURCES

def save_sources(sources: List[Dict[str, Any]]) -> bool:
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
            json.dump({"sources": sources, "updated_at": datetime.now().isoformat()}, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving external sources registry: {e}")
        return False

def add_or_update_source(source_data: Dict[str, Any]) -> Dict[str, Any]:
    sources = load_sources()
    sid = source_data.get("id")
    if not sid:
        raise ValueError("Source 'id' is required.")
    
    idx = next((i for i, s in enumerate(sources) if s["id"] == sid), -1)
    if idx >= 0:
        sources[idx].update(source_data)
        sources[idx]["updated_at"] = datetime.now().isoformat()
    else:
        source_data["created_at"] = datetime.now().isoformat()
        sources.append(source_data)
        
    save_sources(sources)
    return next(s for s in sources if s["id"] == sid)

def toggle_source(source_id: str, enabled: bool) -> Optional[Dict[str, Any]]:
    sources = load_sources()
    for s in sources:
        if s["id"] == source_id:
            s["enabled"] = enabled
            s["updated_at"] = datetime.now().isoformat()
            save_sources(sources)
            return s
    return None

def delete_source(source_id: str) -> bool:
    sources = load_sources()
    new_sources = [s for s in sources if s["id"] != source_id]
    if len(new_sources) != len(sources):
        save_sources(new_sources)
        return True
    return False

def get_active_external_contexts() -> List[Dict[str, Any]]:
    """Returns summaries of active external sources to augment RAG."""
    sources = load_sources()
    active = [s for s in sources if s.get("enabled")]
    return active
