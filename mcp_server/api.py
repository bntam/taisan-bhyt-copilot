"""
FastAPI Server for TaiSanh BHYT Clinical Copilot v2.0
Endpoints:
- POST /api/validate: Validates prescription & procedures against BHYT & YHCT rules
- GET  /api/search-icd: Searches 15,827 official Vietnamese ICD-10 codes
- POST /api/suggest-note: Generates compliant clinical justifications
- POST /api/chat: Real-time Hybrid RAG + Live LLM assistant for doctors
- POST /api/detect-tier: Auto-detects hospital tier (Tuyến 1-4) from facility info/DOM
- POST /api/evaluate-patient: Clinical decision triage, ICD suggestion & regimen
- POST /api/validate-xml130: BHYT XML 130 pre-check before submission
- GET/POST/DELETE /api/sources: Pluggable external MCP & data sources (LangCare, etc.)
- GET  /api/catalog-bundle: Live updated catalog bundle for Chrome Extension
- POST /api/sync-data: Trigger or schedule auto-sync with official sources
- GET  /api/health: Health check, sync metadata status & active sources
"""

from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import os
import json

from .server import (
    validate_prescription,
    search_icd10,
    suggest_clinical_note,
    check_herb_drug_interaction,
    ask_clinical_copilot,
    evaluate_patient,
    DB_PATH
)
from .llm_client import (
    PROVIDER_PRESETS,
    resolve_llm_config,
    test_llm_connection,
    list_available_models,
    mask_api_key
)
from data_engine.cskcb_sync import detect_hospital_tier
from data_engine.xml130_validator import validate_xml130_record as validate_xml130
from data_engine.updater import execute_full_sync as run_full_update, METADATA_PATH
from .external_sources import (
    load_sources,
    add_or_update_source,
    toggle_source,
    delete_source,
    get_active_external_contexts
)

app = FastAPI(title="TaiSanh BHYT Clinical Copilot API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ValidateRequest(BaseModel):
    icd_code: str
    drugs: List[str] = []
    hospital_level: str = "4"
    procedures: Optional[List[str]] = None
    lab_tests: Optional[List[str]] = None
    procedure_days: int = 1

class SuggestNoteRequest(BaseModel):
    icd_code: str
    procedures: List[str] = []
    symptoms: Optional[str] = None

class LlmConfigRequest(BaseModel):
    provider: Optional[str] = "openai_compat"
    api_url: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    enabled: Optional[bool] = True

class ChatRequest(BaseModel):
    message: str
    context: Optional[Dict[str, Any]] = None
    use_llm: bool = True
    llm_config: Optional[LlmConfigRequest] = None

class DetectTierRequest(BaseModel):
    facility_text: Optional[str] = None
    facility_code: Optional[str] = None
    url: Optional[str] = None

class EvaluatePatientRequest(BaseModel):
    symptoms: str
    age: Optional[int] = None
    gender: Optional[str] = None
    vitals: Optional[Dict[str, Any]] = None
    medical_history: Optional[List[str]] = None
    current_drugs: Optional[List[str]] = None
    hospital_level: str = "4"

class Xml130Request(BaseModel):
    xml_content: str
    hospital_level: str = "4"

class SourceItem(BaseModel):
    id: str
    name: str
    type: str
    endpoint: str
    enabled: bool = True
    description: Optional[str] = ""

class ToggleSourceRequest(BaseModel):
    enabled: bool

@app.get("/api/health")
def health():
    meta = {}
    if os.path.exists(METADATA_PATH):
        try:
            with open(METADATA_PATH, "r", encoding="utf-8") as f:
                meta = json.load(f)
        except Exception:
            pass
    return {
        "status": "online",
        "service": "TaiSanh BHYT Clinical Copilot",
        "version": "2.0.0",
        "db_exists": os.path.exists(DB_PATH),
        "metadata": meta,
        "external_sources_active": len(get_active_external_contexts())
    }

@app.post("/api/detect-tier")
def api_detect_tier(req: DetectTierRequest):
    return detect_hospital_tier(
        facility_text=req.facility_text,
        facility_code=req.facility_code,
        url=req.url
    )

@app.post("/api/evaluate-patient")
def api_evaluate_patient(req: EvaluatePatientRequest):
    return evaluate_patient(
        symptoms=req.symptoms,
        age=req.age,
        gender=req.gender,
        vitals=req.vitals,
        medical_history=req.medical_history,
        current_drugs=req.current_drugs,
        hospital_level=req.hospital_level
    )

@app.post("/api/validate-xml130")
def api_validate_xml130(req: Xml130Request):
    record = {}
    if req.xml_content.strip().startswith("{"):
        try:
            record = json.loads(req.xml_content)
        except Exception:
            record = {"raw": req.xml_content}
    else:
        record = {"raw": req.xml_content}
    return validate_xml130(
        record=record,
        hospital_level=req.hospital_level
    )

@app.post("/api/validate")
def api_validate(req: ValidateRequest):
    return validate_prescription(
        icd_code=req.icd_code,
        drugs=req.drugs,
        hospital_level=req.hospital_level,
        procedures=req.procedures,
        lab_tests=req.lab_tests,
        procedure_days=req.procedure_days
    )

@app.get("/api/search-icd")
def api_search_icd(q: str, limit: int = 10):
    return search_icd10(keyword=q, limit=limit)

@app.post("/api/suggest-note")
def api_suggest_note(req: SuggestNoteRequest):
    return suggest_clinical_note(
        icd_code=req.icd_code,
        procedures=req.procedures,
        symptoms=req.symptoms
    )

@app.post("/api/chat")
def api_chat(req: ChatRequest):
    ctx = dict(req.context or {})
    if req.llm_config:
        ctx["llm_config"] = req.llm_config.dict()
    return ask_clinical_copilot(
        query=req.message,
        context=ctx,
        use_llm=req.use_llm
    )

@app.get("/api/llm-presets")
def api_llm_presets():
    current = resolve_llm_config()
    return {
        "presets": PROVIDER_PRESETS,
        "current": {
            "enabled": current["enabled"],
            "provider": current["provider"],
            "api_url": current["api_url"],
            "model": current["model"],
            "key_masked": mask_api_key(current["api_key"]),
            "has_key": bool(current["api_key"])
        }
    }

@app.post("/api/llm-test")
def api_llm_test(req: LlmConfigRequest):
    return test_llm_connection(req.dict())

@app.post("/api/llm-models")
def api_llm_models(req: LlmConfigRequest):
    return list_available_models(req.dict())

@app.get("/api/sources")
def api_list_sources():
    return {"sources": load_sources()}

@app.post("/api/sources")
def api_add_source(source: SourceItem):
    return add_or_update_source(source.dict())

@app.patch("/api/sources/{source_id}/toggle")
def api_toggle_source(source_id: str, req: ToggleSourceRequest):
    res = toggle_source(source_id, req.enabled)
    if not res:
        raise HTTPException(status_code=404, detail="Source not found")
    return res

@app.delete("/api/sources/{source_id}")
def api_delete_source(source_id: str):
    ok = delete_source(source_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Source not found")
    return {"success": True, "deleted": source_id}

@app.get("/api/catalog-bundle")
def api_catalog_bundle():
    bundle_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "extension", "data", "catalog.json")
    if os.path.exists(bundle_path):
        with open(bundle_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"error": "Catalog bundle not generated yet"}

@app.post("/api/sync-data")
def api_sync_data(background_tasks: BackgroundTasks, force: bool = False):
    background_tasks.add_task(run_full_update, force_download=force)
    return {"message": "Data sync initiated in background.", "status": "processing"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8123)
