"""Left pane: Customer identification, financial history (editable tables), and actions.

This module renders:
  - Customer search (existing) or new-customer form
  - Loan history via st.data_editor
  - Transaction history via st.data_editor
  - Evaluate / Save Draft / Reset buttons
"""

from __future__ import annotations

from datetime import date, datetime
from html import escape as html_escape
from math import isnan, isinf

import pandas as pd
import streamlit as st

from app.translations import t, map_to_english, LOAN_STATUS_MAP, TXN_TYPE_MAP
from app.repository import ExcelCustomerRepository, ExcelLoanRepository, ExcelTransactionRepository
from app.ui_components import render_customer_card
from config.business_rules import MIN_DOB, DEFAULT_DOB


# ── Helpers ──

def _clean_value(obj):
    """Recursively clean a value for JSON serialisation."""
    if isinstance(obj, dict):
        return {k: _clean_value(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean_value(i) for i in obj]
    if isinstance(obj, (pd.Timestamp, datetime, date)):
        return obj.strftime("%Y-%m-%d")
    if isinstance(obj, float) and (isnan(obj) or isinf(obj)):
        return None
    if isinstance(obj, str) and obj.strip().lower() == "nan":
        return None
    return obj


def _prepare_api_payload(customer_profile: dict, loan_history: list, transaction_history: list) -> dict:
    """Prepare cleaned payload for the scoring API."""
    return {
        "customer_profile": _clean_value(customer_profile),
        "loan_history": _clean_value(loan_history),
        "transaction_history": _clean_value(transaction_history),
    }


# ── Main render function ──

def render_customer_intake(
    customer_repo: ExcelCustomerRepository,
    loan_repo: ExcelLoanRepository,
    txn_repo: ExcelTransactionRepository,
) -> None:
    """Render the full left-pane customer intake flow."""

    # ── Section 1: Identify Customer ──
    st.subheader(t("identify_customer"))

    customers_df = customer_repo.get_all_customers()
    all_first_names = customer_repo.get_unique_first_names()
    all_last_names = customer_repo.get_unique_last_names()

    is_new = st.toggle(t("new_customer_toggle"), key="is_new_customer")

    if not is_new:
        _render_existing_customer_search(customer_repo, loan_repo, txn_repo, customers_df, all_first_names, all_last_names)
    else:
        _render_new_customer_form(customer_repo, loan_repo, txn_repo, customers_df)

    # ── Section 3: Actions ──
    st.divider()
    st.subheader(t("actions_section"))
    col_btn1, col_btn2, col_btn3 = st.columns(3)

    with col_btn1:
        if st.button(t("evaluate_btn"), type="primary", key="evaluate_btn", use_container_width=True):
            _trigger_evaluation()

    with col_btn2:
        if st.button(t("save_draft_btn"), key="save_draft_btn", use_container_width=True):
            _trigger_save_draft(customer_repo, loan_repo, txn_repo, customers_df)

    with col_btn3:
        if st.button(t("reset_btn"), key="reset_btn", use_container_width=True):
            _reset_state()
            st.rerun()


def _render_existing_customer_search(
    customer_repo, loan_repo, txn_repo, customers_df, all_first_names, all_last_names
) -> None:
    """Search by name first, disambiguate by DOB only when multiple matches."""
    col1, col2 = st.columns(2)

    with col1:
        selected_last = st.session_state.get("selected_last_name", "")
        if selected_last and not customers_df.empty:
            filtered_fn = customer_repo.get_filtered_first_names(selected_last)
            options = filtered_fn + [t("all_names")] + [n for n in all_first_names if n not in filtered_fn]
        else:
            options = all_first_names

        first_name = st.selectbox(
            t("first_name"), options=options, index=None, key="first_name",
            placeholder=t("type_to_search"),
        )
        if first_name == t("all_names"):
            first_name = None
        if not first_name:
            first_name = st.text_input(t("or_enter_first"), key="custom_first_name") or None
        if first_name and first_name != t("all_names"):
            st.session_state.selected_first_name = first_name

    with col2:
        selected_first = st.session_state.get("selected_first_name", "")
        if selected_first and not customers_df.empty:
            filtered_ln = customer_repo.get_filtered_last_names(selected_first)
            options = filtered_ln + [t("all_names")] + [n for n in all_last_names if n not in filtered_ln]
        else:
            options = all_last_names

        last_name = st.selectbox(
            t("last_name"), options=options, index=None, key="last_name",
            placeholder=t("type_to_search"),
        )
        if last_name == t("all_names"):
            last_name = None
        if not last_name:
            last_name = st.text_input(t("or_enter_last"), key="custom_last_name") or None
        if last_name and last_name != t("all_names"):
            st.session_state.selected_last_name = last_name

    if st.button(t("search_btn"), type="primary", key="search_btn"):
        if not first_name or not last_name:
            st.warning(t("enter_both_names"))
        else:
            matches = customer_repo.find_customers_by_name(first_name, last_name)
            st.session_state.search_performed = True

            if len(matches) == 1:
                # Unique match — select immediately
                _select_customer(matches[0], loan_repo, txn_repo, first_name)
            elif len(matches) > 1:
                # Multiple matches — store for DOB disambiguation
                st.session_state.customer_found = False
                st.session_state.name_matches = matches
                st.session_state.customer_data = None
            else:
                st.session_state.customer_found = False
                st.session_state.name_matches = []
                st.session_state.customer_data = None
                st.session_state.loan_data = []
                st.session_state.transaction_data = []
                st.info(t("new_customer"))

    # ── DOB disambiguation (shown when multiple name matches) ──
    matches = st.session_state.get("name_matches", [])
    if matches and not st.session_state.get("customer_found"):
        st.info(t("multiple_matches").format(count=len(matches)))
        dob_options = []
        for m in matches:
            raw = m.get("DateOfBirth")
            try:
                if isinstance(raw, str):
                    d = date.fromisoformat(raw[:10])
                elif isinstance(raw, date):
                    d = raw
                elif hasattr(raw, "date") and callable(raw.date):
                    d = raw.date()
                else:
                    d = None
            except (ValueError, AttributeError):
                d = None
            dob_options.append(d)

        dob_labels = [d.strftime("%Y-%m-%d") if d else "Unknown" for d in dob_options]
        selected_dob = st.selectbox(
            t("select_dob"), options=range(len(dob_labels)),
            format_func=lambda i: dob_labels[i], key="disambig_dob",
        )
        if st.button(t("confirm_btn"), key="confirm_dob_btn"):
            _select_customer(matches[selected_dob], loan_repo, txn_repo, matches[selected_dob].get("FirstName", ""))
            st.session_state.name_matches = []
            st.rerun()

    # Show customer data if found
    if st.session_state.get("search_performed") and st.session_state.get("customer_found"):
        customer_data = st.session_state.customer_data
        render_customer_card(customer_data)
        _render_financial_history_tabs()


def _select_customer(record: dict, loan_repo, txn_repo, first_name: str) -> None:
    """Populate session state from a selected customer record."""
    st.session_state.customer_found = True
    st.session_state.customer_data = _clean_value(record)
    customer_id = record.get("CustomerID", "")
    loans_df = loan_repo.get_loans_for_customer(customer_id)
    txns_df = txn_repo.get_transactions_for_customer(customer_id)
    st.session_state.loan_data = _clean_value(loans_df.to_dict("records")) if not loans_df.empty else []
    st.session_state.transaction_data = _clean_value(txns_df.to_dict("records")) if not txns_df.empty else []
    st.success(t("welcome_back").format(name=html_escape(first_name)))


def _render_new_customer_form(customer_repo, loan_repo, txn_repo, customers_df) -> None:
    """Render the new customer input form."""
    st.markdown(f'<div class="info-box">{html_escape(t("new_customer_info"))}</div>', unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        new_first = st.text_input(t("first_name_input"), key="new_first")
        new_last = st.text_input(t("last_name_input"), key="new_last")
    with col2:
        new_middle = st.text_input(t("middle_name"), key="new_middle")
        new_date_reg = st.date_input(t("date_registered_input"), value=date.today(), key="new_reg")

    col3, col4 = st.columns(2)
    with col3:
        new_country = st.text_input(t("country_input"), key="new_country")
    with col4:
        new_dependents = st.number_input(t("dependents_input"), min_value=0, max_value=20, value=0, key="new_dependents")

    dob = st.date_input(t("dob"), min_value=MIN_DOB, max_value=date.today(), value=DEFAULT_DOB, key="new_dob")

    # Store for later use (only when names are filled)
    if new_first.strip() and new_last.strip():
        st.session_state.new_customer_form = {
            "FirstName": new_first.strip(),
            "LastName": new_last.strip(),
            "MiddleName": new_middle.strip(),
            "DateOfBirth": dob.isoformat(),
            "DateRegistered": new_date_reg.isoformat(),
            "Country": new_country.strip(),
            "NumberOfDependents": new_dependents,
            "Defaulted": 0,
        }
    else:
        st.session_state.new_customer_form = None

    _render_financial_history_tabs()


def _render_financial_history_tabs() -> None:
    """Render loan and transaction history using st.data_editor in tabs."""
    st.subheader(t("financial_history"))
    loan_tab, txn_tab = st.tabs([t("loans_tab"), t("transactions_tab")])

    with loan_tab:
        existing_loans = st.session_state.get("loan_data", [])
        if existing_loans:
            st.caption(t("loan_history_label").format(count=len(existing_loans)))

        loan_columns = {
            "LoanApplicationDate": st.column_config.DateColumn(t("loan_date"), required=True),
            "Amount": st.column_config.NumberColumn(t("amount"), min_value=1, required=True),
            "NumberOfEMIs": st.column_config.NumberColumn(t("num_emis"), min_value=1, required=True),
            "LoanStatus": st.column_config.SelectboxColumn(
                t("status"),
                options=t("loan_statuses"),
                required=True,
            ),
        }

        default_loan_df = pd.DataFrame(existing_loans) if existing_loans else pd.DataFrame(
            columns=["LoanApplicationDate", "Amount", "NumberOfEMIs", "LoanStatus"]
        )
        # Ensure date column is datetime
        if "LoanApplicationDate" in default_loan_df.columns and not default_loan_df.empty:
            default_loan_df["LoanApplicationDate"] = pd.to_datetime(default_loan_df["LoanApplicationDate"], errors="coerce")

        edited_loans = st.data_editor(
            default_loan_df,
            column_config=loan_columns,
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            key="loan_editor",
        )
        st.session_state.edited_loans = edited_loans

    with txn_tab:
        existing_txns = st.session_state.get("transaction_data", [])
        if existing_txns:
            st.caption(t("txn_history_label").format(count=len(existing_txns)))

        txn_columns = {
            "TransactionDate": st.column_config.DateColumn(t("date_col").replace("**", ""), required=True),
            "Amount": st.column_config.NumberColumn(t("amount"), min_value=1, required=True),
            "Type": st.column_config.SelectboxColumn(
                t("type_col").replace("**", ""),
                options=t("txn_types"),
                required=True,
            ),
        }

        default_txn_df = pd.DataFrame(existing_txns) if existing_txns else pd.DataFrame(
            columns=["TransactionDate", "Amount", "Type"]
        )
        if "TransactionDate" in default_txn_df.columns and not default_txn_df.empty:
            default_txn_df["TransactionDate"] = pd.to_datetime(default_txn_df["TransactionDate"], errors="coerce")

        edited_txns = st.data_editor(
            default_txn_df,
            column_config=txn_columns,
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            key="txn_editor",
        )
        st.session_state.edited_transactions = edited_txns


def _trigger_evaluation() -> None:
    """Gather data from session state and call the scoring API."""
    from app.api_client import ScoringAPIClient, ServiceUnavailableError, ScoringError, ValidationError

    # Build customer profile
    customer_data = st.session_state.get("customer_data")
    new_form = st.session_state.get("new_customer_form")

    if customer_data:
        profile = customer_data
    elif new_form:
        if not new_form.get("FirstName") or not new_form.get("LastName"):
            st.error(t("names_required"))
            return
        profile = new_form
    else:
        st.warning(t("enter_both_names"))
        return

    # Collect loans from data editor
    edited_loans = st.session_state.get("edited_loans")
    loan_records = []
    if edited_loans is not None and not edited_loans.empty:
        for _, row in edited_loans.dropna(subset=["Amount"]).iterrows():
            status_val = row.get("LoanStatus", "Closed")
            status_en = map_to_english(LOAN_STATUS_MAP, str(status_val))
            loan_records.append({
                "LoanApplicationDate": _clean_value(row.get("LoanApplicationDate", date.today())),
                "Amount": float(row.get("Amount", 0)),
                "NumberOfEMIs": int(row.get("NumberOfEMIs", 12)),
                "LoanStatus": status_en,
            })

    # Collect transactions from data editor
    edited_txns = st.session_state.get("edited_transactions")
    txn_records = []
    if edited_txns is not None and not edited_txns.empty:
        for _, row in edited_txns.dropna(subset=["Amount"]).iterrows():
            txn_type_val = row.get("Type", "Incoming")
            txn_type_en = map_to_english(TXN_TYPE_MAP, str(txn_type_val))
            txn_records.append({
                "TransactionDate": _clean_value(row.get("TransactionDate", date.today())),
                "Amount": float(row.get("Amount", 0)),
                "Type": txn_type_en,
            })

    payload = _prepare_api_payload(profile, loan_records, txn_records)

    client = ScoringAPIClient()
    try:
        with st.spinner(t("calculating")):
            result = client.evaluate_customer(payload)
            st.session_state.evaluation_result = result
            st.session_state.api_payload = payload
            st.session_state.show_results = True
    except ServiceUnavailableError:
        st.error(t("service_unavailable_msg"))
    except ValidationError as exc:
        st.warning(t("validation_error").format(details=exc.detail))
    except ScoringError:
        st.error(t("scoring_error"))


def _trigger_save_draft(customer_repo, loan_repo, txn_repo, customers_df) -> None:
    """Save customer data without evaluating."""
    new_form = st.session_state.get("new_customer_form")
    if not new_form or not new_form.get("FirstName") or not new_form.get("LastName"):
        st.warning(t("names_required"))
        return

    try:
        customer_id = customer_repo.generate_customer_id()
        new_form["CustomerID"] = customer_id
        customer_repo.save_customer(new_form)

        # Save loans
        edited_loans = st.session_state.get("edited_loans")
        if edited_loans is not None and not edited_loans.empty:
            loan_records = []
            for _, row in edited_loans.dropna(subset=["Amount"]).iterrows():
                status_en = map_to_english(LOAN_STATUS_MAP, str(row.get("LoanStatus", "Closed")))
                loan_records.append({
                    "CustomerID": customer_id,
                    "LoanApplicationDate": _clean_value(row.get("LoanApplicationDate")),
                    "Amount": float(row.get("Amount", 0)),
                    "NumberOfEMIs": int(row.get("NumberOfEMIs", 12)),
                    "LoanStatus": status_en,
                })
            loan_repo.save_loans(loan_records)

        # Save transactions
        edited_txns = st.session_state.get("edited_transactions")
        if edited_txns is not None and not edited_txns.empty:
            txn_records = []
            for _, row in edited_txns.dropna(subset=["Amount"]).iterrows():
                txn_type_en = map_to_english(TXN_TYPE_MAP, str(row.get("Type", "Incoming")))
                txn_records.append({
                    "CustomerID": customer_id,
                    "TransactionDate": _clean_value(row.get("TransactionDate")),
                    "Amount": float(row.get("Amount", 0)),
                    "Type": txn_type_en,
                })
            txn_repo.save_transactions(txn_records)

        st.success(t("saved_msg").format(cid=customer_id))
    except Exception as e:
        st.error(t("save_error").format(err=str(e)))


def _reset_state() -> None:
    """Clear all session state related to customer input and results."""
    keys_to_clear = [
        "customer_found", "customer_data", "loan_data", "transaction_data",
        "search_performed", "selected_first_name", "selected_last_name",
        "new_customer_form", "evaluation_result", "show_results",
        "api_payload", "edited_loans", "edited_transactions",
    ]
    for key in keys_to_clear:
        if key in st.session_state:
            del st.session_state[key]
