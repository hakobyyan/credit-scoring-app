"""Environment-driven application settings.

All hardcoded values (ports, URLs, model tags, file paths) are centralised here
and can be overridden via environment variables or a `.env` file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


def _project_root() -> Path:
    """Return the project root (one level above this file's directory)."""
    return Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    # ── Networking ──
    api_url: str = field(default_factory=lambda: os.environ.get("API_URL", "http://localhost:3000"))
    api_timeout: int = field(default_factory=lambda: int(os.environ.get("API_TIMEOUT", "30")))
    bentoml_port: int = field(default_factory=lambda: int(os.environ.get("BENTOML_PORT", "3000")))
    streamlit_port: int = field(default_factory=lambda: int(os.environ.get("STREAMLIT_PORT", "8501")))

    # ── Model ──
    model_tag: str = field(default_factory=lambda: os.environ.get("MODEL_TAG", "credit_scoring:latest"))

    # ── Paths ──
    data_dir: Path = field(default_factory=lambda: Path(os.environ.get("DATA_DIR", str(_project_root() / "data"))))
    venv_path: Path = field(default_factory=lambda: Path(os.environ.get("VENV_PATH", str(_project_root().parent / ".venv"))))

    # ── Excel file names (relative to data_dir) ──
    customers_file: str = field(default_factory=lambda: os.environ.get("CUSTOMERS_FILE", "customer_profiles_5000.xlsx"))
    loans_file: str = field(default_factory=lambda: os.environ.get("LOANS_FILE", "loan_history_5000.xlsx"))
    transactions_file: str = field(default_factory=lambda: os.environ.get("TRANSACTIONS_FILE", "transaction_history_5000.xlsx"))

    # ── Feature list ──
    selected_features_file: str = "selected_features.json"

    @property
    def customers_path(self) -> Path:
        return self.data_dir / self.customers_file

    @property
    def loans_path(self) -> Path:
        return self.data_dir / self.loans_file

    @property
    def transactions_path(self) -> Path:
        return self.data_dir / self.transactions_file

    @property
    def selected_features_path(self) -> Path:
        return self.data_dir / self.selected_features_file


settings = Settings()
