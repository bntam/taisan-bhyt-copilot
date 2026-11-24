#!/usr/bin/env python3
"""
Standard Model Context Protocol (MCP) Stdio Server for TaiSanh BHYT Clinical Copilot
Compliant with MCP specification (JSON-RPC 2.0 over stdio).
Usable directly with:
- Claude Desktop (`claude_desktop_config.json`)
- Cursor IDE (`.cursor/mcp.json`)
- Hermes Agent / LangChain / Any MCP Client
"""

import sys
import json
import logging
import traceback
from typing import Dict, Any, List

# Configure logger to write to stderr so stdout is strictly reserved for JSON-RPC
logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="[MCP-BHYT] %(levelname)s: %(message)s")

try:
    from mcp_server.server import (
        validate_prescription,
        search_icd10,
        suggest_clinical_note,
        check_herb_drug_interaction,
        ask_clinical_copilot,
        get_db
    )
    from data_engine.updater import execute_full_sync
except ImportError:
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from mcp_server.server import (
        validate_prescription,
        search_icd10,
        suggest_clinical_note,
        check_herb_drug_interaction,
        ask_clinical_copilot,
        get_db
    )
    from data_engine.updater import execute_full_sync

SERVER_NAME = "taisan-bhyt-copilot"
SERVER_VERSION = "1.1.0"

TOOLS_MANIFEST = [
    {
        "name": "validate_prescription",
        "description": "Validates outpatient/inpatient prescriptions and procedures against Vietnamese BHYT audit rules (TT 20/2022, TT 27/2020, TT 13/2019) to prevent financial rejections (chống xuất toán).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "icd_code": {"type": "string", "description": "ICD-10 diagnosis code (e.g. 'M54.5', 'E11.9', 'I10')"},
                "drugs": {"type": "array", "items": {"type": "string"}, "description": "List of prescribed drugs with strengths (e.g. ['Paracetamol 500mg', 'Ceftriaxone 1g'])"},
                "hospital_level": {"type": "string", "enum": ["1", "2", "3", "4"], "default": "4", "description": "Hospital technical tier ('4' for private clinic / commune health station, '3' for district, '2' for provincial, '1' for central)"},
                "procedures": {"type": "array", "items": {"type": "string"}, "description": "List of indicated procedures (e.g. ['Điện châm điều trị', 'Xoa bóp bấm huyệt'])"},
                "lab_tests": {"type": "array", "items": {"type": "string"}, "description": "Recorded paraclinical/lab tests (e.g. ['Lipid máu', 'Glucose', 'X-quang'])"},
                "procedure_days": {"type": "integer", "default": 1, "description": "Number of consecutive treatment days indicated"}
            },
            "required": ["icd_code"]
        }
    },
    {
        "name": "search_icd10",
        "description": "Full-text search over 15,827 official Vietnamese ICD-10 disease codes with BHYT regulatory flags (must use 4-digit subcode, forbidden primary code).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "Keyword in Vietnamese with/without accents or ICD code (e.g. 'thoát vị đĩa đệm', 'M54')"},
                "limit": {"type": "integer", "default": 10, "description": "Max results to return"}
            },
            "required": ["keyword"]
        }
    },
    {
        "name": "check_herb_drug_interaction",
        "description": "Detects hazardous herb-drug interactions between Vietnamese Traditional Medicine (YHCT) and Western pharmacology (e.g. Dan Shen with anticoagulants, Licorice with antihypertensives).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tcm_herbs": {"type": "array", "items": {"type": "string"}, "description": "List of traditional herbs (e.g. ['Đan sâm', 'Đương quy', 'Cam thảo'])"},
                "western_drugs": {"type": "array", "items": {"type": "string"}, "description": "List of western pharmaceutical drugs (e.g. ['Aspirin', 'Warfarin', 'Amlodipine'])"}
            },
            "required": ["tcm_herbs", "western_drugs"]
        }
    },
    {
        "name": "suggest_clinical_note",
        "description": "Generates compliant physical examination descriptions, clinical findings, and TCM differentiation matching ICD-10 to safeguard BHYT reimbursement.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "icd_code": {"type": "string", "description": "Primary ICD-10 code (e.g. 'M54.5')"},
                "procedures": {"type": "array", "items": {"type": "string"}, "description": "Procedures being justified"},
                "symptoms": {"type": "string", "description": "Optional patient presenting symptoms"}
            },
            "required": ["icd_code"]
        }
    },
    {
        "name": "ask_clinical_copilot",
        "description": "Consult the clinical knowledge engine about BHYT regulations, drug eligibility by hospital tier, procedure duration caps, or TCM herb pharmacology.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Question in Vietnamese or English (e.g. 'Cam thảo có dùng cho người tăng huyết áp không?', 'Thuốc giảm đau tuyến 4')"},
                "hospital_level": {"type": "string", "default": "4", "description": "Hospital tier"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "sync_catalog_data",
        "description": "Trigger catalog synchronization and verify checksums against official Ministry of Health databases.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "force": {"type": "boolean", "default": False, "description": "Force redownload and rebuild entire database"}
            }
        }
    }
]

def handle_initialize(req_id: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {
                    "listChanged": False
                }
            },
            "serverInfo": {
                "name": SERVER_NAME,
                "version": SERVER_VERSION
            }
        }
    }

def handle_tools_list(req_id: Any) -> Dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {
            "tools": TOOLS_MANIFEST
        }
    }

def handle_tools_call(req_id: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    name = params.get("name")
    args = params.get("arguments", {})
    
    try:
        if name == "validate_prescription":
            res = validate_prescription(
                icd_code=args.get("icd_code", ""),
                drugs=args.get("drugs", []),
                hospital_level=args.get("hospital_level", "4"),
                procedures=args.get("procedures", []),
                lab_tests=args.get("lab_tests", []),
                procedure_days=args.get("procedure_days", 1)
            )
            content_text = json.dumps(res, ensure_ascii=False, indent=2)
        elif name == "search_icd10":
            res = search_icd10(
                keyword=args.get("keyword", ""),
                limit=args.get("limit", 10)
            )
            content_text = json.dumps(res, ensure_ascii=False, indent=2)
        elif name == "check_herb_drug_interaction":
            res = check_herb_drug_interaction(
                tcm_herbs=args.get("tcm_herbs", []),
                western_drugs=args.get("western_drugs", [])
            )
            content_text = json.dumps(res, ensure_ascii=False, indent=2)
        elif name == "suggest_clinical_note":
            res = suggest_clinical_note(
                icd_code=args.get("icd_code", ""),
                procedures=args.get("procedures", []),
                symptoms=args.get("symptoms", None)
            )
            content_text = json.dumps(res, ensure_ascii=False, indent=2)
        elif name == "ask_clinical_copilot":
            res = ask_clinical_copilot(
                query=args.get("query", ""),
                context={"hospital_level": args.get("hospital_level", "4")}
            )
            content_text = res.get("answer", "")
            if res.get("suggested_snippet"):
                content_text += f"\n\n**Mô tả gợi ý:**\n```\n{res['suggested_snippet']}\n```"
        elif name == "sync_catalog_data":
            res = execute_full_sync(force_download=bool(args.get("force", False)))
            content_text = json.dumps(res, ensure_ascii=False, indent=2)
        else:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32601,
                    "message": f"Tool '{name}' not found"
                }
            }
        
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": content_text
                    }
                ]
            }
        }
    except Exception as e:
        logging.error(f"Error in tools/call for {name}: {traceback.format_exc()}")
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": -32000,
                "message": str(e)
            }
        }

def process_line(line: str):
    if not line.strip():
        return
    try:
        req = json.loads(line)
    except json.JSONDecodeError as err:
        logging.error(f"Invalid JSON: {err}")
        return

    req_id = req.get("id")
    method = req.get("method")
    params = req.get("params", {})

    response = None
    if method == "initialize":
        response = handle_initialize(req_id, params)
    elif method == "notifications/initialized":
        # Client notification, no reply needed
        return
    elif method == "tools/list":
        response = handle_tools_list(req_id)
    elif method == "tools/call":
        response = handle_tools_call(req_id, params)
    elif method == "ping":
        response = {"jsonrpc": "2.0", "id": req_id, "result": {}}
    else:
        if req_id is not None:
            response = {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32601,
                    "message": f"Method '{method}' not implemented"
                }
            }

    if response is not None:
        sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        sys.stdout.flush()

def main():
    logging.info(f"Starting {SERVER_NAME} v{SERVER_VERSION} on stdio...")
    for line in sys.stdin:
        process_line(line)

if __name__ == "__main__":
    main()
