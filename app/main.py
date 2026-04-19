"""Streamlit application entry point — single-page advisor dashboard.

Customer intake at top, score results below.
"""

from __future__ import annotations

import sys
from html import escape as html_escape
from pathlib import Path

import streamlit as st

# ── Make project root importable ──
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.translations import t, TRANSLATIONS
from app.ui_components import render_global_css, render_health_indicator
from app.api_client import ScoringAPIClient, ServiceUnavailableError
from app.repository import ExcelCustomerRepository, ExcelLoanRepository, ExcelTransactionRepository
from app.pages.customer_intake import render_customer_intake
from app.pages.results_panel import render_results_panel
from config.business_rules import DEFAULT_DOB


def main() -> None:
    st.set_page_config(page_title="Credit Score Check", page_icon="💳", layout="wide")
    render_global_css()

    # ── Sidebar ──
    with st.sidebar:
        _render_sidebar_health()
        _render_sidebar_help()

    # ── Init session state ──
    _defaults = {
        "customer_found": None,
        "customer_data": None,
        "loan_data": None,
        "transaction_data": None,
        "show_results": False,
        "search_performed": False,
        "selected_first_name": "",
        "selected_last_name": "",
        "name_matches": [],
        "dob": DEFAULT_DOB,
    }
    for key, default in _defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default

    # ── Header with language selector top-right ──
    header_col, lang_col = st.columns([4, 1])
    with header_col:
        st.markdown(
            f'<h1 class="main-header">{html_escape(t("main_header"))}</h1>',
            unsafe_allow_html=True,
        )
    with lang_col:
        st.selectbox(
            "🌐",
            options=list(TRANSLATIONS.keys()),
            key="language",
            label_visibility="collapsed",
        )
    st.markdown(
        f'<p class="main-subtitle">{html_escape(t("step1_info"))}</p>',
        unsafe_allow_html=True,
    )

    # ── Customer intake ──
    customer_repo = ExcelCustomerRepository()
    loan_repo = ExcelLoanRepository()
    txn_repo = ExcelTransactionRepository()
    render_customer_intake(customer_repo, loan_repo, txn_repo)

    # ── Results ──
    st.divider()
    render_results_panel()

    # ── Footer ──
    st.divider()
    st.markdown(
        f'''<div style="text-align: center; color: #888; padding: 1.5rem 1rem 0.5rem; font-size: 0.85rem;">
        <p style="margin-bottom:0.3rem;">{t("footer_tip")}</p>
        <p style="margin:0;">{t("footer_security")}</p>
        </div>''',
        unsafe_allow_html=True,
    )


# ── Sidebar helpers ──

@st.cache_data(ttl=10)
def _check_health() -> dict | None:
    try:
        client = ScoringAPIClient()
        return client.check_health()
    except ServiceUnavailableError:
        return None


def _render_sidebar_health() -> None:
    st.markdown("---")
    st.markdown(t("service_status"))
    health = _check_health()
    render_health_indicator(health)


def _render_sidebar_help() -> None:
    st.markdown("---")
    st.header(t("help_header"))
    st.markdown(f"### {t('how_to_use')}")
    st.markdown(t("help_steps"))

    st.markdown(f"### {t('understanding_score')}")
    score_table = f"""
| Score | Level |
|-------|-------|
| 751-900 | {t('very_low_risk')} |
| 651-750 | {t('low_risk')} |
| 551-650 | {t('moderate_risk')} |
| 350-550 | {t('high_risk')} |"""
    st.markdown(score_table)

    st.markdown(f"### {t('need_help')}")
    st.markdown(t("help_issues"))


if __name__ == "__main__":
    main()
else:
    main()
