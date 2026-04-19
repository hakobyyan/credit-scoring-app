"""Repository abstraction for data persistence.

Currently backed by Excel files.  The abstract interface allows swapping
to SQLite / Postgres later without touching application code.
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from datetime import date
from typing import Optional

import pandas as pd
import streamlit as st

from config.settings import settings

logger = logging.getLogger(__name__)


# ── Sanitisation helpers ──

def _sanitize_for_excel(value):
    """Sanitize string values to prevent Excel formula injection (CWE-1236)."""
    if isinstance(value, str):
        stripped = value.lstrip()
        if stripped and stripped[0] in ("=", "+", "@", "\t", "\r"):
            return "'" + value
        if stripped and stripped[0] == "-" and (len(stripped) < 2 or not stripped[1].isdigit()):
            return "'" + value
    return value


def _sanitize_dict(d: dict) -> dict:
    """Sanitize all string values in a dict for safe Excel writing."""
    return {k: _sanitize_for_excel(v) for k, v in d.items()}


# ── Abstract interfaces ──

class CustomerRepository(ABC):
    @abstractmethod
    def get_all_customers(self) -> pd.DataFrame: ...

    @abstractmethod
    def find_customer(self, first_name: str, last_name: str, dob: date) -> Optional[dict]: ...

    @abstractmethod
    def find_customers_by_name(self, first_name: str, last_name: str) -> list[dict]: ...

    @abstractmethod
    def get_unique_first_names(self) -> list[str]: ...

    @abstractmethod
    def get_unique_last_names(self) -> list[str]: ...

    @abstractmethod
    def save_customer(self, profile: dict) -> str: ...

    @abstractmethod
    def generate_customer_id(self) -> str: ...


class LoanRepository(ABC):
    @abstractmethod
    def get_loans_for_customer(self, customer_id: str) -> pd.DataFrame: ...

    @abstractmethod
    def save_loans(self, loans: list[dict]) -> None: ...


class TransactionRepository(ABC):
    @abstractmethod
    def get_transactions_for_customer(self, customer_id: str) -> pd.DataFrame: ...

    @abstractmethod
    def save_transactions(self, transactions: list[dict]) -> None: ...


# ── Module-level cached loaders (avoids unhashable-self issues) ──

@st.cache_data(ttl=30)
def _load_excel(path: str) -> pd.DataFrame:
    """Read an Excel file, strip column whitespace, return a DataFrame."""
    try:
        if not os.path.exists(path):
            logger.warning("Data file not found: %s", path)
            return pd.DataFrame()
        df = pd.read_excel(path)
        df.columns = df.columns.str.strip()
        return df
    except Exception as e:
        logger.error("Failed to load %s: %s", path, e)
        return pd.DataFrame()


# ── Excel implementations ──

class ExcelCustomerRepository(CustomerRepository):
    def __init__(self, file_path: str | os.PathLike | None = None):
        self._path = str(file_path or settings.customers_path)

    def _df(self) -> pd.DataFrame:
        return _load_excel(self._path)

    def get_all_customers(self) -> pd.DataFrame:
        return self._df()

    def find_customer(self, first_name: str, last_name: str, dob: date) -> Optional[dict]:
        df = self._df()
        if df.empty:
            return None
        dob_col = pd.to_datetime(df["DateOfBirth"], errors="coerce").dt.date
        mask = (
            (df["FirstName"].str.lower() == first_name.lower())
            & (df["LastName"].str.lower() == last_name.lower())
            & (dob_col == dob)
        )
        match = df[mask]
        return match.iloc[0].to_dict() if not match.empty else None

    def find_customers_by_name(self, first_name: str, last_name: str) -> list[dict]:
        df = self._df()
        if df.empty:
            return []
        mask = (
            (df["FirstName"].str.lower() == first_name.lower())
            & (df["LastName"].str.lower() == last_name.lower())
        )
        matches = df[mask]
        return matches.to_dict("records") if not matches.empty else []

    def get_unique_first_names(self) -> list[str]:
        df = self._df()
        if df.empty:
            return []
        return sorted(df["FirstName"].dropna().unique().tolist())

    def get_unique_last_names(self) -> list[str]:
        df = self._df()
        if df.empty:
            return []
        return sorted(df["LastName"].dropna().unique().tolist())

    def generate_customer_id(self) -> str:
        df = self._df()
        if df.empty:
            return "CUST000001"
        max_num = 0
        for cid in df["CustomerID"].tolist():
            try:
                num = int(str(cid).replace("CUST", ""))
                max_num = max(max_num, num)
            except Exception:
                pass
        return f"CUST{str(max_num + 1).zfill(6)}"

    def save_customer(self, profile: dict) -> str:
        df = self._df()
        new_row = pd.DataFrame([_sanitize_dict(profile)])
        updated = pd.concat([df, new_row], ignore_index=True)
        updated.to_excel(self._path, index=False)
        _load_excel.clear()
        return profile.get("CustomerID", "")

    def get_filtered_first_names(self, last_name: str) -> list[str]:
        df = self._df()
        if df.empty:
            return []
        return sorted(
            df[df["LastName"].str.strip().str.lower() == last_name.strip().lower()]["FirstName"].dropna().unique().tolist()
        )

    def get_filtered_last_names(self, first_name: str) -> list[str]:
        df = self._df()
        if df.empty:
            return []
        return sorted(
            df[df["FirstName"].str.strip().str.lower() == first_name.strip().lower()]["LastName"].dropna().unique().tolist()
        )


class ExcelLoanRepository(LoanRepository):
    def __init__(self, file_path: str | os.PathLike | None = None):
        self._path = str(file_path or settings.loans_path)

    def _df(self) -> pd.DataFrame:
        return _load_excel(self._path)

    def get_loans_for_customer(self, customer_id: str) -> pd.DataFrame:
        df = self._df()
        if df.empty or "CustomerID" not in df.columns:
            return pd.DataFrame()
        return df[df["CustomerID"] == customer_id]

    def save_loans(self, loans: list[dict]) -> None:
        if not loans:
            return
        df = self._df()
        new_rows = pd.DataFrame([_sanitize_dict(row) for row in loans])
        updated = pd.concat([df, new_rows], ignore_index=True)
        updated.to_excel(self._path, index=False)
        _load_excel.clear()


class ExcelTransactionRepository(TransactionRepository):
    def __init__(self, file_path: str | os.PathLike | None = None):
        self._path = str(file_path or settings.transactions_path)

    def _df(self) -> pd.DataFrame:
        return _load_excel(self._path)

    def get_transactions_for_customer(self, customer_id: str) -> pd.DataFrame:
        df = self._df()
        if df.empty or "CustomerID" not in df.columns:
            return pd.DataFrame()
        return df[df["CustomerID"] == customer_id]

    def save_transactions(self, transactions: list[dict]) -> None:
        if not transactions:
            return
        df = self._df()
        new_rows = pd.DataFrame([_sanitize_dict(row) for row in transactions])
        updated = pd.concat([df, new_rows], ignore_index=True)
        updated.to_excel(self._path, index=False)
        _load_excel.clear()
