"""FastAPI backend — serves static UI and REST endpoints for CRUD + BentoML proxy."""

from __future__ import annotations

import logging
import math
from datetime import date, datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.api_client import (
    ScoringAPIClient,
    ScoringError,
    ServiceUnavailableError,
    ValidationError,
)
from app.repository import (
    ExcelCustomerRepository,
    ExcelLoanRepository,
    ExcelTransactionRepository,
)
from app.translations import FEATURE_DISPLAY_NAMES_I18N, LOAN_STATUS_MAP, TRANSLATIONS, TXN_TYPE_MAP
from config.business_rules import (
    CREDIT_TYPES,
    FEATURE_DISPLAY_NAMES,
    RISK_TIERS,
    SCORE_MAX,
    SCORE_MIN,
)
from config.settings import settings

logger = logging.getLogger(__name__)

app = FastAPI(title="Credit Scoring App")

_allowed_origins = [
    f"http://localhost:{settings.webapp_port}",
    f"http://127.0.0.1:{settings.webapp_port}",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Repositories (singletons) ──
customer_repo = ExcelCustomerRepository()
loan_repo = ExcelLoanRepository()
txn_repo = ExcelTransactionRepository()

# ── Scoring API client ──
scoring_client = ScoringAPIClient()

# ── Static files ──
STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ── Pydantic models for request bodies ──


class CustomerSearchRequest(BaseModel):
    first_name: str
    last_name: str
    dob: str | None = None  # ISO date string


class SaveCustomerRequest(BaseModel):
    CustomerID: str | None = None
    FirstName: str
    LastName: str
    MiddleName: str | None = ""
    DateOfBirth: str
    DateRegistered: str | None = None
    Country: str | None = ""
    NumberOfDependents: int | None = 0
    Defaulted: int | None = 0


class LoanInput(BaseModel):
    LoanApplicationDate: str | None = None
    Amount: float
    NumberOfEMIs: int
    LoanStatus: str
    CustomerID: str | None = None


class TransactionInput(BaseModel):
    TransactionDate: str
    Amount: float
    Type: str
    CustomerID: str | None = None


class EvaluateRequest(BaseModel):
    customer_profile: dict
    loan_history: list[dict] = []
    transaction_history: list[dict] = []


# ── Helpers ──


def _clean_value(v):
    """Make a value JSON-safe (handle NaN, Timestamp, date, etc.)."""
    if v is None:
        return None
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    if isinstance(v, datetime):
        return v.isoformat()[:10]
    if isinstance(v, date):
        return v.isoformat()
    if hasattr(v, "isoformat"):
        return str(v)
    return v


def _clean_dict(d: dict) -> dict:
    return {k: _clean_value(v) for k, v in d.items()}


def _records_to_json(df) -> list[dict]:
    """Convert a DataFrame to a list of JSON-safe dicts."""
    if df is None or df.empty:
        return []
    return [_clean_dict(row) for row in df.to_dict("records")]


# ── Root: serve index.html ──


@app.get("/")
async def root():
    return FileResponse(str(STATIC_DIR / "index.html"))


# ── Customer endpoints ──


@app.get("/api/customers/first-names")
async def get_first_names(last_name: str | None = Query(None)):
    if last_name:
        return customer_repo.get_filtered_first_names(last_name)
    return customer_repo.get_unique_first_names()


@app.get("/api/customers/last-names")
async def get_last_names(first_name: str | None = Query(None)):
    if first_name:
        return customer_repo.get_filtered_last_names(first_name)
    return customer_repo.get_unique_last_names()


@app.post("/api/customers/search")
async def search_customers(req: CustomerSearchRequest):
    if req.dob:
        try:
            dob_date = date.fromisoformat(req.dob)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid date format for dob")
        cust = customer_repo.find_customer(req.first_name, req.last_name, dob_date)
        if cust:
            return {"matches": [_clean_dict(cust)]}
        return {"matches": []}
    matches = customer_repo.find_customers_by_name(req.first_name, req.last_name)
    return {"matches": [_clean_dict(m) for m in matches]}


@app.get("/api/customers/{customer_id}/loans")
async def get_customer_loans(customer_id: str):
    df = loan_repo.get_loans_for_customer(customer_id)
    return _records_to_json(df)


@app.get("/api/customers/{customer_id}/transactions")
async def get_customer_transactions(customer_id: str):
    df = txn_repo.get_transactions_for_customer(customer_id)
    return _records_to_json(df)


@app.post("/api/customers")
async def save_customer(req: SaveCustomerRequest):
    profile = req.model_dump()
    if not profile.get("CustomerID"):
        profile["CustomerID"] = customer_repo.generate_customer_id()
    cid = customer_repo.save_customer(profile)
    return {"CustomerID": cid}


@app.post("/api/customers/{customer_id}/loans")
async def save_customer_loans(customer_id: str, loans: list[LoanInput]):
    records = [loan.model_dump() for loan in loans]
    for record in records:
        record["CustomerID"] = customer_id
    loan_repo.save_loans(records)
    return {"saved": len(records)}


@app.post("/api/customers/{customer_id}/transactions")
async def save_customer_transactions(customer_id: str, transactions: list[TransactionInput]):
    records = [txn.model_dump() for txn in transactions]
    for record in records:
        record["CustomerID"] = customer_id
    txn_repo.save_transactions(records)
    return {"saved": len(records)}


# ── Evaluation proxy ──


@app.post("/api/evaluate")
async def evaluate(req: EvaluateRequest):
    payload = {
        "customer_profile": req.customer_profile,
        "loan_history": req.loan_history,
        "transaction_history": req.transaction_history,
    }
    try:
        result = scoring_client.evaluate_customer(payload)
        return result
    except ServiceUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.detail)
    except ScoringError as e:
        raise HTTPException(status_code=502, detail=str(e))


# ── Health proxy ──


@app.get("/api/health")
async def health():
    try:
        result = scoring_client.check_health()
        return result
    except ServiceUnavailableError:
        return {"status": "offline", "model_loaded": False}


# ── Config / translations ──


@app.get("/api/translations")
async def get_translations():
    return {
        "translations": TRANSLATIONS,
        "loan_status_map": LOAN_STATUS_MAP,
        "txn_type_map": TXN_TYPE_MAP,
        "feature_display_names_i18n": FEATURE_DISPLAY_NAMES_I18N,
    }


@app.get("/api/business-rules")
async def get_business_rules():
    return {
        "score_min": SCORE_MIN,
        "score_max": SCORE_MAX,
        "risk_tiers": RISK_TIERS,
        "credit_types": CREDIT_TYPES,
        "feature_display_names": FEATURE_DISPLAY_NAMES,
    }
