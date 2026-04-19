"""BentoML Credit Scoring Service — unified endpoint with SHAP explanations.

Provides a single ``evaluate_customer`` endpoint that returns the full
evaluation result (score, risk, probability, BMRC, FMRC, explanations,
eligible products) in one call.  A ``/health`` endpoint is also exposed.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import bentoml

# ── Make project root importable ──
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from config.business_rules import (
    SCORE_MIN,
    SCORE_MAX,
    SCORE_FORMULA_FACTOR,
    DATA_COMPLETENESS_MONTHS,
    FEATURE_DISPLAY_NAMES,
    get_risk_level,
    get_risk_tier,
    get_eligible_products,
)
from config.settings import settings

logger = logging.getLogger("credit_scoring_service")

# ── Load selected features list ──
_features_path = settings.selected_features_path
with open(_features_path) as f:
    SELECTED_FEATURES: list[str] = json.load(f)


# ═══════════════════════════════════════════════════════════════
# Feature engineering (unchanged logic from original service.py)
# ═══════════════════════════════════════════════════════════════

def prepare_features_from_json(json_input: dict) -> pd.DataFrame:
    """Build the 21-feature vector from raw customer/loan/txn data."""
    customer_df = pd.DataFrame([json_input["customer_profile"]])
    loan_df = pd.DataFrame(json_input.get("loan_history", []))
    txn_df = pd.DataFrame(json_input.get("transaction_history", []))

    customer_df["DateRegistered"] = pd.to_datetime(customer_df["DateRegistered"])
    customer_df["DateOfBirth"] = pd.to_datetime(customer_df["DateOfBirth"])

    # ── No loan history path ──
    if loan_df.empty or "LoanApplicationDate" not in loan_df.columns:
        if not txn_df.empty and "TransactionDate" in txn_df.columns:
            txn_df["TransactionDate"] = pd.to_datetime(txn_df["TransactionDate"])
            txn_df["SignedAmount"] = txn_df.apply(
                lambda row: row["Amount"] if row["Type"] == "Incoming" else -row["Amount"],
                axis=1,
            )
            app_date = txn_df["TransactionDate"].max()
            sum_3m = txn_df[txn_df["TransactionDate"] > app_date - pd.Timedelta(days=90)]["SignedAmount"].sum()
            sum_6m = txn_df[txn_df["TransactionDate"] > app_date - pd.Timedelta(days=180)]["SignedAmount"].sum()
            txn_count = txn_df.shape[0]
            txn_avg = float(txn_df["SignedAmount"].mean())
            last_txn_days_ago = 0
            incoming = txn_df[txn_df["SignedAmount"] > 0]["SignedAmount"].sum()
            outgoing = -txn_df[txn_df["SignedAmount"] < 0]["SignedAmount"].sum()
            out_in_ratio = outgoing / incoming if incoming else 0
            recent_out_ratio = outgoing / (abs(sum_3m) + 1e-6)
        else:
            app_date = pd.Timestamp.today()
            txn_avg = sum_6m = sum_3m = txn_count = last_txn_days_ago = 0
            out_in_ratio = recent_out_ratio = 0

        feature_vector = {
            "PreviouslyDefaulted": 0,
            "Txn_Avg": txn_avg,
            "Txn_Sum_6M": sum_6m,
            "Hist_DaysSinceLastLoan": 0,
            "LoanAmountToTxnNetRatio": 0,
            "Amount": 0,
            "Hist_MonthsSinceFirstLoan": 0,
            "AgeToLoanRatio": 0,
            "DaysSinceRegistration": (app_date - customer_df.iloc[0]["DateRegistered"]).days,
            "Txn_Sum_3M": sum_3m,
            "Hist_LoanFrequencyPerYear": 0,
            "ApplicationWeekday": app_date.weekday(),
            "Hist_ShortTermLoanShare": 0,
            "Hist_AvgLoanGap": 0,
            "Txn_Count": txn_count,
            "Hist_MeanEMIs": 0,
            "OutgoingToIncomingRatio": out_in_ratio,
            "Txn_LastDaysAgo": last_txn_days_ago,
            "Hist_MaxAmount": 0,
            "RecentOutRatio": recent_out_ratio,
            "CustomerAgeAtApplication": (app_date - customer_df.iloc[0]["DateOfBirth"]).days // 365,
        }
        return pd.DataFrame([feature_vector])[SELECTED_FEATURES]

    # ── Full loan-history path ──
    loan_df["LoanApplicationDate"] = pd.to_datetime(loan_df["LoanApplicationDate"])
    txn_df["TransactionDate"] = pd.to_datetime(txn_df["TransactionDate"])
    txn_df["SignedAmount"] = txn_df.apply(
        lambda row: row["Amount"] if row["Type"] == "Incoming" else -row["Amount"],
        axis=1,
    )

    loan_df = loan_df.sort_values(by="LoanApplicationDate")
    app_date = loan_df.iloc[-1]["LoanApplicationDate"]
    history = loan_df[loan_df["LoanApplicationDate"] < app_date]

    count_loans = len(history)
    short_term_loans = history[history["NumberOfEMIs"] <= 6].shape[0]
    short_term_ratio = short_term_loans / count_loans if count_loans else 0
    days_since_last = (app_date - history["LoanApplicationDate"].max()).days if not history.empty else 0
    months_since_first = (app_date - history["LoanApplicationDate"].min()).days // 30 if not history.empty else 0
    avg_loan_gap = (
        history["LoanApplicationDate"].sort_values().diff().dropna().dt.days.mean()
        if len(history) > 1
        else 0
    )
    loans_per_year = count_loans / (months_since_first / 12) if months_since_first else 0
    mean_emis = history["NumberOfEMIs"].mean() if not history.empty else 0
    max_amt = history["Amount"].max() if not history.empty else 0

    age_at_app = (app_date - customer_df.iloc[0]["DateOfBirth"]).days // 365
    days_since_reg = (app_date - customer_df.iloc[0]["DateRegistered"]).days

    recent_txns = txn_df[txn_df["TransactionDate"] < app_date]
    sum_3m = recent_txns[recent_txns["TransactionDate"] > app_date - pd.Timedelta(days=90)]["SignedAmount"].sum()
    sum_6m = recent_txns[recent_txns["TransactionDate"] > app_date - pd.Timedelta(days=180)]["SignedAmount"].sum()
    txn_count = recent_txns.shape[0]
    txn_avg = recent_txns["SignedAmount"].mean() if not recent_txns.empty else 0
    last_txn_days_ago = (app_date - recent_txns["TransactionDate"].max()).days if not recent_txns.empty else 0

    incoming = recent_txns[recent_txns["SignedAmount"] > 0]["SignedAmount"].sum()
    outgoing = -recent_txns[recent_txns["SignedAmount"] < 0]["SignedAmount"].sum()
    out_in_ratio = outgoing / incoming if incoming else 0

    feature_vector = {
        "PreviouslyDefaulted": int(history["LoanStatus"].eq("Defaulted").any()),
        "Txn_Avg": txn_avg,
        "Txn_Sum_6M": sum_6m,
        "Hist_DaysSinceLastLoan": days_since_last,
        "LoanAmountToTxnNetRatio": loan_df.iloc[-1]["Amount"] / (abs(sum_6m) + 1e-6),
        "Amount": loan_df.iloc[-1]["Amount"],
        "Hist_MonthsSinceFirstLoan": months_since_first,
        "AgeToLoanRatio": age_at_app / (loan_df.iloc[-1]["Amount"] + 1e-6),
        "DaysSinceRegistration": days_since_reg,
        "Txn_Sum_3M": sum_3m,
        "Hist_LoanFrequencyPerYear": loans_per_year,
        "ApplicationWeekday": app_date.weekday(),
        "Hist_ShortTermLoanShare": short_term_ratio,
        "Hist_AvgLoanGap": avg_loan_gap,
        "Txn_Count": txn_count,
        "Hist_MeanEMIs": mean_emis,
        "OutgoingToIncomingRatio": out_in_ratio,
        "Txn_LastDaysAgo": last_txn_days_ago,
        "Hist_MaxAmount": max_amt,
        "RecentOutRatio": outgoing / (abs(sum_3m) + 1e-6),
        "CustomerAgeAtApplication": age_at_app,
    }
    return pd.DataFrame([feature_vector])[SELECTED_FEATURES]


# ═══════════════════════════════════════════════════════════════
# Prediction helpers
# ═══════════════════════════════════════════════════════════════

def _predict_proba(model, features: pd.DataFrame) -> float:
    """Get default probability from model.  Raises on failure."""
    if hasattr(model, "predict_proba"):
        p = model.predict_proba(features)
        if p.ndim == 2:
            return float(p[0, 1])
        return float(p[0])
    else:
        import xgboost as xgb

        d = xgb.DMatrix(features)
        p = model.predict(d)
        if p.ndim == 1:
            return float(p[0])
        return float(p[0, 1])


def _compute_transaction_months(json_input: dict) -> int:
    """Count distinct months of transaction data in the last 180 days."""
    txn_df = pd.DataFrame(json_input.get("transaction_history", []))
    if txn_df.empty or "TransactionDate" not in txn_df.columns:
        return 0
    txn_df["TransactionDate"] = pd.to_datetime(txn_df["TransactionDate"])
    latest_date = txn_df["TransactionDate"].max()
    recent = txn_df[txn_df["TransactionDate"] >= latest_date - pd.Timedelta(days=180)]
    return min(DATA_COMPLETENESS_MONTHS, recent["TransactionDate"].dt.to_period("M").nunique())


def _compute_bmrc(json_input: dict) -> float:
    """Balance Monthly Rolling Cash — avg monthly net cash flow over 6 months."""
    txn_df = pd.DataFrame(json_input.get("transaction_history", []))
    if txn_df.empty or "TransactionDate" not in txn_df.columns:
        return 0.0
    txn_df["TransactionDate"] = pd.to_datetime(txn_df["TransactionDate"])
    txn_df["SignedAmount"] = txn_df.apply(
        lambda row: row["Amount"] if row["Type"] == "Incoming" else -row["Amount"],
        axis=1,
    )
    latest_date = txn_df["TransactionDate"].max()
    txn_df = txn_df[txn_df["TransactionDate"] >= latest_date - pd.Timedelta(days=180)]
    txn_df["YearMonth"] = txn_df["TransactionDate"].dt.to_period("M")
    monthly_net = txn_df.groupby("YearMonth")["SignedAmount"].sum()
    if len(monthly_net) == 0:
        return 0.0
    return round(float(monthly_net.mean()), 2)


def _compute_shap_explanations(
    explainer, features: pd.DataFrame, top_n: int = 5
) -> list[dict]:
    """Return top-N SHAP-based feature explanations for a single prediction."""
    shap_values = explainer.shap_values(features)
    if isinstance(shap_values, list):
        # For multi-class, take the positive-class (index 1)
        vals = shap_values[1][0]
    else:
        vals = shap_values[0]

    feature_names = features.columns.tolist()
    abs_vals = np.abs(vals)
    top_indices = np.argsort(abs_vals)[::-1][:top_n]

    explanations = []
    for idx in top_indices:
        fname = feature_names[idx]
        contribution = float(vals[idx])
        explanations.append({
            "feature_name": fname,
            "display_name": FEATURE_DISPLAY_NAMES.get(fname, fname),
            "contribution": round(contribution, 4),
            "direction": "increases_risk" if contribution > 0 else "decreases_risk",
        })
    return explanations


# ═══════════════════════════════════════════════════════════════
# BentoML Service
# ═══════════════════════════════════════════════════════════════

model_ref = bentoml.xgboost.get(settings.model_tag)
model_runner = model_ref.load_model()


@bentoml.service(
    name="credit_scoring",
    traffic={"timeout": 60},
)
class CreditScoringService:

    def __init__(self) -> None:
        self.model = model_runner
        self.model_tag = settings.model_tag

        # Initialise SHAP explainer (TreeExplainer is fast for XGBoost)
        try:
            import shap

            self.explainer = shap.TreeExplainer(self.model)
            logger.info("SHAP TreeExplainer initialised successfully")
        except Exception as exc:
            logger.warning("SHAP explainer could not be initialised: %s", exc)
            self.explainer = None

    # ── Unified evaluation endpoint ──
    @bentoml.api
    def evaluate_customer(self, json_input: dict) -> dict:
        """Single endpoint that returns score, risk, probability, BMRC, FMRC,
        SHAP explanations, data completeness, and eligible products."""
        features = prepare_features_from_json(json_input)
        prob_default = _predict_proba(self.model, features)

        # Credit score with data-completeness penalty
        raw_score = max(SCORE_MIN, int(SCORE_MAX - (prob_default * SCORE_FORMULA_FACTOR)))
        months_available = _compute_transaction_months(json_input)
        completeness_factor = 0.5 + 0.5 * (months_available / DATA_COMPLETENESS_MONTHS)
        score = max(SCORE_MIN, int(SCORE_MIN + (raw_score - SCORE_MIN) * completeness_factor))
        score = min(SCORE_MAX, score)

        risk_level = get_risk_level(score)
        risk_style = get_risk_tier(score)

        # Cash-flow metrics
        bmrc = _compute_bmrc(json_input)
        fmrc = round(bmrc * (1 - prob_default), 2)

        # Data completeness info
        if months_available >= DATA_COMPLETENESS_MONTHS:
            confidence = "full"
            detail = f"{months_available} months of transaction data"
        elif months_available >= 3:
            confidence = "partial"
            detail = f"{months_available} months — result confidence reduced"
        else:
            confidence = "minimal"
            detail = f"Only {months_available} month(s) — limited data, score may be conservative"

        # SHAP explanations
        explanations = []
        explanations_available = self.explainer is not None
        if explanations_available:
            try:
                explanations = _compute_shap_explanations(self.explainer, features, top_n=5)
            except Exception as exc:
                logger.error("SHAP explanation failed: %s", exc)
                explanations_available = False

        # Eligible products
        eligible_products = get_eligible_products(score)

        return {
            "credit_score": score,
            "risk_level": risk_level,
            "risk_color": risk_style["color"],
            "default_probability": int(np.round(prob_default * 100)),
            "bmrc": bmrc,
            "fmrc": fmrc,
            "data_completeness": {
                "months_available": months_available,
                "confidence": confidence,
                "detail": detail,
            },
            "explanations": explanations,
            "eligible_products": eligible_products,
        }

    # ── Health endpoint ──
    @bentoml.api
    def health(self) -> dict:
        """Basic health / readiness check."""
        return {
            "status": "ok",
            "model_loaded": self.model is not None,
            "version": self.model_tag,
        }

    # ── Deprecated endpoints (kept for backward compatibility) ──

    @bentoml.api
    def predict_probability(self, json_input: dict) -> dict:
        """(Deprecated) Use evaluate_customer instead."""
        features = prepare_features_from_json(json_input)
        prob_default = _predict_proba(self.model, features)
        return {"DefaultProbability": int(np.round(prob_default * 100))}

    @bentoml.api
    def predict_credit_score(self, json_input: dict) -> dict:
        """(Deprecated) Use evaluate_customer instead."""
        result = self.evaluate_customer(json_input)
        return {"CreditScore": result["credit_score"], "Risk Level": result["risk_level"]}

    @bentoml.api
    def calculate_fmrc(self, json_input: dict) -> dict:
        """(Deprecated) Use evaluate_customer instead."""
        result = self.evaluate_customer(json_input)
        return {"FMRC": result["fmrc"]}
