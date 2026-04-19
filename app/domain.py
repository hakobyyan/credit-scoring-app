"""Pure domain / calculation logic — no Streamlit dependency.

Functions here are deterministic and unit-testable.
"""

from __future__ import annotations

import pandas as pd


def calculate_monthly_payment(
    principal: float, annual_rate: float, term_months: int
) -> float:
    """Standard amortization monthly payment."""
    if principal <= 0 or term_months <= 0 or annual_rate < 0:
        return 0.0
    r = annual_rate / 12
    if r == 0:
        return principal / term_months
    return principal * r * (1 + r) ** term_months / ((1 + r) ** term_months - 1)


def calculate_max_loan_amount(
    max_monthly_payment: float, annual_rate: float, term_months: int
) -> float:
    """Reverse amortization: max principal from affordable monthly payment."""
    if max_monthly_payment <= 0 or annual_rate <= 0 or term_months <= 0:
        return 0.0
    r = annual_rate / 12
    return max(0, round(max_monthly_payment * ((1 - (1 + r) ** (-term_months)) / r), 2))


def calculate_dti(total_monthly_debt: float, gross_monthly_income: float) -> float:
    """Debt-to-income ratio."""
    if gross_monthly_income <= 0:
        return 0.0
    return total_monthly_debt / gross_monthly_income


def get_max_amount_for_dti(
    gross_income: float,
    existing_debt: float,
    max_dti: float,
    annual_rate: float,
    term_months: int,
) -> float:
    """Maximum loan amount that keeps DTI within the limit."""
    max_new_payment = (gross_income * max_dti) - existing_debt
    if max_new_payment <= 0:
        return 0.0
    return calculate_max_loan_amount(max_new_payment, annual_rate, term_months)


def generate_repayment_schedule(
    principal: float, annual_rate: float, term_months: int
) -> pd.DataFrame:
    """Month-by-month amortization schedule.

    Returns a DataFrame with English column names.  The caller is
    responsible for renaming to translated labels if needed.
    """
    r = annual_rate / 12
    payment = calculate_monthly_payment(principal, annual_rate, term_months)

    schedule = []
    balance = principal
    for month in range(1, term_months + 1):
        interest = balance * r
        principal_payment = payment - interest
        balance = max(0, balance - principal_payment)
        schedule.append(
            {
                "Month": month,
                "Payment": round(payment, 2),
                "Principal": round(principal_payment, 2),
                "Interest": round(interest, 2),
                "Remaining Balance": round(balance, 2),
            }
        )
    return pd.DataFrame(schedule)
