"""Single source of truth for all business rules.

Both the BentoML service and the Streamlit UI import from here,
eliminating the risk of rules drifting between layers.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional

logger = logging.getLogger(__name__)

# ── Score constants ──
SCORE_MIN = 350
SCORE_MAX = 900
SCORE_FORMULA_FACTOR = 550  # score = 900 - (prob * 550)
DATA_COMPLETENESS_MONTHS = 6  # full confidence requires 6 months of txn data

# ── Threshold constants (kept for convenience) ──
SCORE_VERY_LOW_RISK_MIN = 751
SCORE_LOW_RISK_MIN = 651
SCORE_MODERATE_RISK_MIN = 551
MIN_DOB = date(1920, 1, 1)
DEFAULT_DOB = date(1990, 1, 1)

# ── Risk tier definitions ──
RISK_TIERS = [
    {
        "name": "Very Low Risk",
        "min_score": SCORE_VERY_LOW_RISK_MIN,
        "css_class": "very-low-risk",
        "color": "#28a745",
        "bg": "#d4edda",
        "range": "751-900",
    },
    {
        "name": "Low Risk",
        "min_score": SCORE_LOW_RISK_MIN,
        "css_class": "low-risk",
        "color": "#007bff",
        "bg": "#cce5ff",
        "range": "651-750",
    },
    {
        "name": "Moderate Risk",
        "min_score": SCORE_MODERATE_RISK_MIN,
        "css_class": "moderate-risk",
        "color": "#ffc107",
        "bg": "#fff3cd",
        "range": "551-650",
    },
    {
        "name": "High Risk",
        "min_score": 0,
        "css_class": "high-risk",
        "color": "#dc3545",
        "bg": "#f8d7da",
        "range": "350-550",
    },
]


def get_risk_level(score: int) -> str:
    """Map a credit score to a risk level name."""
    for tier in RISK_TIERS:
        if score >= tier["min_score"]:
            return tier["name"]
    return "High Risk"


def get_risk_tier(score: int) -> dict:
    """Return the full RISK_TIERS entry for a given score."""
    for tier in RISK_TIERS:
        if score >= tier["min_score"]:
            return tier
    return RISK_TIERS[-1]


# ── Credit product definitions (realistic US market rates, 2024-2025) ──
CREDIT_TYPES = {
    "personal": {
        "min_score": 580,
        "min_term_months": 12,
        "max_term_months": 84,
        "min_amount": 100,
        "max_amount": 50_000,
        "max_dti": 0.43,
        "rates": {
            "High Risk": 0.22,
            "Moderate Risk": 0.16,
            "Low Risk": 0.12,
            "Very Low Risk": 0.08,
        },
    },
    "mortgage": {
        "min_score": 620,
        "min_term_months": 60,
        "max_term_months": 360,
        "min_amount": 50_000,
        "max_amount": 1_000_000,
        "max_dti": 0.43,
        "min_down_pct": 0.05,
        "max_ltv": 0.95,
        "rates": {
            "High Risk": 0.085,
            "Moderate Risk": 0.075,
            "Low Risk": 0.065,
            "Very Low Risk": 0.0575,
        },
    },
    "auto": {
        "min_score": 500,
        "min_term_months": 24,
        "max_term_months": 84,
        "min_amount": 5_000,
        "max_amount": 100_000,
        "max_dti": 0.43,
        "max_ltv": 1.20,
        "rates": {
            "High Risk": 0.14,
            "Moderate Risk": 0.095,
            "Low Risk": 0.065,
            "Very Low Risk": 0.045,
        },
    },
    "education": {
        "min_score": 670,
        "min_term_months": 60,
        "max_term_months": 240,
        "min_amount": 1_000,
        "max_amount": 150_000,
        "max_dti": 0.43,
        "rates": {
            "High Risk": 0.12,
            "Moderate Risk": 0.09,
            "Low Risk": 0.07,
            "Very Low Risk": 0.05,
        },
    },
    "business": {
        "min_score": 680,
        "min_term_months": 12,
        "max_term_months": 300,
        "min_amount": 10_000,
        "max_amount": 500_000,
        "max_dti": 0.43,
        "rates": {
            "High Risk": 0.16,
            "Moderate Risk": 0.12,
            "Low Risk": 0.09,
            "Very Low Risk": 0.07,
        },
    },
    "secured": {
        "min_score": 580,
        "min_term_months": 12,
        "max_term_months": 180,
        "min_amount": 5_000,
        "max_amount": 500_000,
        "max_dti": 0.45,
        "max_ltv": 0.80,
        "rates": {
            "High Risk": 0.11,
            "Moderate Risk": 0.08,
            "Low Risk": 0.06,
            "Very Low Risk": 0.045,
        },
    },
}


def get_eligible_products(score: int) -> list[dict]:
    """Return product configs for which the given score meets the minimum."""
    results = []
    for key, config in CREDIT_TYPES.items():
        results.append({
            "product_type": key,
            "eligible": score >= config["min_score"],
            "min_score": config["min_score"],
            "rate": get_rate_for_tier(key, get_risk_level(score)),
            "max_amount": config["max_amount"],
        })
    return results


def get_rate_for_tier(product_key: str, risk_level: str) -> Optional[float]:
    """Look up annual interest rate for a product + risk tier."""
    config = CREDIT_TYPES.get(product_key)
    if config is None:
        return None
    rate = config["rates"].get(risk_level)
    if rate is None:
        logger.warning("Unknown risk level '%s' for product '%s', using High Risk rate", risk_level, product_key)
        rate = config["rates"].get("High Risk", 0.24)
    return rate


# Human-readable feature name mapping for SHAP explanations
FEATURE_DISPLAY_NAMES = {
    "PreviouslyDefaulted": "Previous Defaults",
    "Txn_Avg": "Avg Transaction Amount",
    "Txn_Sum_6M": "Net Cash Flow (6 months)",
    "Txn_Sum_3M": "Net Cash Flow (3 months)",
    "Txn_Count": "Transaction Count",
    "Txn_LastDaysAgo": "Days Since Last Transaction",
    "OutgoingToIncomingRatio": "Outgoing/Incoming Ratio",
    "RecentOutRatio": "Recent Outgoing Ratio",
    "Hist_DaysSinceLastLoan": "Days Since Last Loan",
    "Hist_MonthsSinceFirstLoan": "Months Since First Loan",
    "Hist_LoanFrequencyPerYear": "Loans Per Year",
    "Hist_AvgLoanGap": "Avg Gap Between Loans",
    "Hist_ShortTermLoanShare": "Short-term Loan Share",
    "Hist_MeanEMIs": "Avg Installments Per Loan",
    "Hist_MaxAmount": "Max Historical Loan Amount",
    "LoanAmountToTxnNetRatio": "Loan-to-Cash-Flow Ratio",
    "AgeToLoanRatio": "Age-to-Loan Ratio",
    "Amount": "Current Loan Amount",
    "DaysSinceRegistration": "Days Since Registration",
    "ApplicationWeekday": "Application Day of Week",
    "CustomerAgeAtApplication": "Customer Age",
}
