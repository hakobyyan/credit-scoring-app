"""Pydantic models for the API contract between the service and the UI.

Used by both the BentoML service (input validation, response construction)
and the Streamlit API client (response parsing).
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ── Enums ──

class LoanStatus(str, Enum):
    CLOSED = "Closed"
    ACTIVE = "Active"
    DEFAULTED = "Defaulted"


class TransactionType(str, Enum):
    INCOMING = "Incoming"
    OUTGOING = "Outgoing"


# ── Request models ──

class CustomerProfile(BaseModel):
    CustomerID: Optional[str] = None
    FirstName: str
    LastName: str
    MiddleName: Optional[str] = None
    DateOfBirth: date
    DateRegistered: date
    Country: Optional[str] = ""
    NumberOfDependents: Optional[int] = 0
    Defaulted: Optional[int] = 0

    @field_validator("DateOfBirth")
    @classmethod
    def validate_dob(cls, v: date) -> date:
        if v < date(1920, 1, 1):
            raise ValueError("DateOfBirth must be after 1920-01-01")
        if v > date.today():
            raise ValueError("DateOfBirth cannot be in the future")
        return v

    @field_validator("DateRegistered")
    @classmethod
    def validate_date_registered(cls, v: date) -> date:
        if v > date.today():
            raise ValueError("DateRegistered cannot be in the future")
        return v


class LoanRecord(BaseModel):
    LoanApplicationDate: date
    Amount: float = Field(gt=0)
    NumberOfEMIs: int = Field(gt=0)
    LoanStatus: LoanStatus
    CustomerID: Optional[str] = None


class TransactionRecord(BaseModel):
    TransactionDate: date
    Amount: float = Field(gt=0)
    Type: TransactionType
    CustomerID: Optional[str] = None


class EvaluationRequest(BaseModel):
    customer_profile: CustomerProfile
    loan_history: list[LoanRecord] = Field(default_factory=list, max_length=10_000)
    transaction_history: list[TransactionRecord] = Field(default_factory=list, max_length=50_000)


# ── Response models ──

class ScoreExplanation(BaseModel):
    feature_name: str
    display_name: str
    contribution: float
    direction: str  # "increases_risk" or "decreases_risk"


class DataCompleteness(BaseModel):
    months_available: int
    confidence: str  # "full", "partial", "minimal"
    detail: str  # human-readable like "6 months of transaction data"


class ProductEligibility(BaseModel):
    product_type: str
    eligible: bool
    min_score: int
    rate: Optional[float] = None
    max_amount: int


class EvaluationResponse(BaseModel):
    credit_score: int
    risk_level: str
    risk_color: str
    default_probability: int  # 0-100
    bmrc: float
    fmrc: float
    data_completeness: DataCompleteness
    explanations: list[ScoreExplanation] = Field(default_factory=list)
    eligible_products: list[ProductEligibility] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str  # "ok" or "error"
    model_loaded: bool
    version: str
