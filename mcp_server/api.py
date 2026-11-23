"""
FastAPI Server for TaiSanh BHYT Clinical Copilot
Endpoints:
- POST /api/validate: Validates prescription & procedures against BHYT & YHCT rules
- GET  /api/search-icd: Searches 15,827 official Vietnamese ICD-10 codes
- POST /api/suggest-note: Generates compliant clinical justifications
- POST /api/sync-data: Trigger or schedule auto-sync with official sources
- GET  /api/health: Health check and sync metadata status
"""

from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import os
import json

from .server import validate_prescription, search_icd10, suggest_clinical_note, check_herb_drug_interaction, DB_PATH
from data_engine.sync_catalog import sync_catalog, METADATA_PATH

app = FastAPI(title="TaiSanh BHYT Clinical Copilot API", version="1.0.0")

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
        "db_exists": os.path.exists(DB_PATH),
        "metadata": meta
    }

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

@app.post("/api/sync-data")
def api_sync_data(background_tasks: BackgroundTasks, force: bool = False):
    background_tasks.add_task(sync_catalog, force=force)
    return {"message": "Data sync initiated in background.", "status": "processing"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8123)
