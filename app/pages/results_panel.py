"""Right pane: Evaluation results, product cards, and loan calculator.

This module renders the sticky results panel showing:
  - Score card with risk badge
  - Data completeness indicator
  - Default probability
  - Why This Score? (SHAP explanations)
  - FMRC / affordability
  - Product cards grid
  - Expandable loan calculator per product
"""

from __future__ import annotations

from html import escape as html_escape

import pandas as pd
import streamlit as st

from app.translations import t
from app.domain import (
    calculate_monthly_payment,
    calculate_max_loan_amount,
    generate_repayment_schedule,
)
from app.ui_components import (
    render_score_card,
    render_score_interpretation,
    render_data_completeness_badge,
    render_explanation_panel,
    render_metric_row,
    render_dti_bar,
    render_product_card,
)
from config.business_rules import (
    CREDIT_TYPES,
    get_risk_level,
    get_rate_for_tier,
)


def render_results_panel() -> None:
    """Render the right pane results panel."""
    evaluation = st.session_state.get("evaluation_result")

    if not st.session_state.get("show_results"):
        st.markdown(
            f'<div style="text-align:center;color:#888;padding:3rem 1rem;">'
            f'{html_escape(t("results_placeholder"))}</div>',
            unsafe_allow_html=True,
        )
        return

    if not evaluation:
        st.error(t("scoring_error"))
        return

    # ── Score Card ──
    render_score_card(evaluation)

    # ── Data Completeness ──
    completeness = evaluation.get("data_completeness", {})
    st.markdown(f"#### {t('data_completeness')}")
    render_data_completeness_badge(completeness)

    # ── Default Probability ──
    prob = evaluation.get("default_probability", 0)
    st.metric(t("default_probability"), f"{prob}%")

    # ── Score Interpretation ──
    score = evaluation.get("credit_score", 0)
    render_score_interpretation(score)

    st.divider()

    # ── Why This Score? ──
    explanations = evaluation.get("explanations", [])
    render_explanation_panel(explanations)

    st.divider()

    # ── Affordability / FMRC ──
    fmrc = evaluation.get("fmrc", 0)
    bmrc = evaluation.get("bmrc", 0)
    st.markdown(f"#### {t('affordability')}")
    render_metric_row([
        ("BMRC", f"${bmrc:,.2f}/mo"),
        ("FMRC", f"${fmrc:,.2f}/mo"),
    ], highlight_idx=1)
    st.caption(t("monthly_cash_flow"))

    st.divider()

    # ── Eligible Products ──
    products = evaluation.get("eligible_products", [])
    st.markdown(f"#### {t('product_cards_header')}")

    # Render product cards in a grid (2 columns)
    eligible_products = [p for p in products if p.get("eligible")]
    ineligible_products = [p for p in products if not p.get("eligible")]

    if eligible_products:
        cols = st.columns(2)
        for i, product in enumerate(eligible_products):
            with cols[i % 2]:
                render_product_card(product)

    if ineligible_products:
        with st.expander(f"{t('not_eligible_badge')} ({len(ineligible_products)})", expanded=False):
            cols = st.columns(2)
            for i, product in enumerate(ineligible_products):
                with cols[i % 2]:
                    render_product_card(product)

    st.divider()

    # ── Loan Calculator (expanded for selected product) ──
    if eligible_products:
        _render_loan_calculator(score, fmrc, eligible_products)


def _render_loan_calculator(
    credit_score: int,
    fmrc_value: float,
    eligible_products: list[dict],
) -> None:
    """Render the loan calculator section with product selection."""
    st.markdown(f"#### {t('loan_calculator')}")

    product_keys = [p["product_type"] for p in eligible_products]
    product_labels = {k: t(f"credit_{k}") for k in product_keys}

    selected_key = st.selectbox(
        t("select_credit_type"),
        options=product_keys,
        format_func=lambda k: product_labels.get(k, k),
        key="calc_product_select",
    )

    config = CREDIT_TYPES.get(selected_key)
    if config is None:
        st.error(t("scoring_error"))
        return
    risk_level = get_risk_level(credit_score)
    annual_rate = get_rate_for_tier(selected_key, risk_level) or 0.10

    # ── Income & debt ──
    st.markdown(f"##### {t('income_section')}")
    if fmrc_value > 0:
        st.info(t("fmrc_reference").format(amount=f"{fmrc_value:,.2f}"))

    gross_income = st.number_input(
        t("gross_income_input"), min_value=0.0, value=5000.0, step=100.0, key="calc_gross_income",
    )
    if gross_income <= 0:
        return

    with st.expander(t("existing_debt_header"), expanded=False):
        st.caption(t("existing_debt_info"))
        dc1, dc2 = st.columns(2)
        with dc1:
            debt_housing = st.number_input(t("debt_housing"), min_value=0.0, value=0.0, step=50.0, key="calc_debt_housing")
            debt_auto = st.number_input(t("debt_auto"), min_value=0.0, value=0.0, step=50.0, key="calc_debt_auto")
            debt_cc = st.number_input(t("debt_credit_cards"), min_value=0.0, value=0.0, step=50.0, key="calc_debt_cc")
        with dc2:
            debt_student = st.number_input(t("debt_student_loans"), min_value=0.0, value=0.0, step=50.0, key="calc_debt_student")
            debt_other = st.number_input(t("debt_other"), min_value=0.0, value=0.0, step=50.0, key="calc_debt_other")

    existing_debt = debt_housing + debt_auto + debt_cc + debt_student + debt_other
    max_dti = config["max_dti"]
    current_dti = existing_debt / gross_income if gross_income > 0 else 0.0

    render_metric_row([
        (t("total_existing_debt"), f"${existing_debt:,.0f}/mo"),
        (t("dti_ratio_label"), f"{current_dti:.1%}"),
    ])
    render_dti_bar(current_dti, max_dti)

    if current_dti >= max_dti:
        st.error(t("dti_too_high").format(dti=current_dti, max_dti=max_dti))
        return

    # ── Term & rate ──
    min_term = config.get("min_term_months", 12)
    max_term = config["max_term_months"]
    term_months = st.slider(
        t("loan_term_months"), min_value=min_term, max_value=max_term,
        value=min(60, max_term), step=6, key="calc_term_slider",
    )

    # ── Type-specific inputs ──
    asset_cap = float("inf")

    if selected_key == "mortgage":
        st.markdown(f"##### {t('mortgage_details')}")
        property_value = st.number_input(
            t("property_value_mortgage"), min_value=0.0, value=300000.0, step=10000.0,
            key="calc_property_value",
        )
        if property_value <= 0:
            st.warning(t("enter_both_names"))
            return
        min_down_pct = config.get("min_down_pct", 0.05)
        down_pct = st.slider(
            t("down_payment_pct"),
            min_value=int(min_down_pct * 100), max_value=50,
            value=max(20, int(min_down_pct * 100)), step=1,
            key="calc_down_pct",
            help=t("min_down_required").format(pct=int(min_down_pct * 100)),
        )
        down_payment = property_value * (down_pct / 100)
        requested_loan = property_value - down_payment
        ltv_limit = property_value * config.get("max_ltv", 0.95)
        asset_cap = min(requested_loan, ltv_limit)
        mc1, mc2 = st.columns(2)
        mc1.metric(t("down_payment_amount"), f"${down_payment:,.0f}")
        mc2.metric(t("loan_amount_after_down"), f"${requested_loan:,.0f}")

    elif selected_key == "auto":
        st.markdown(f"##### {t('auto_details')}")
        ac1, ac2 = st.columns(2)
        with ac1:
            vehicle_price = st.number_input(
                t("vehicle_price"), min_value=0.0, value=30000.0, step=1000.0,
                key="calc_vehicle_price",
            )
        if vehicle_price <= 0:
            st.warning(t("enter_both_names"))
            return
        with ac2:
            down_payment = st.number_input(
                t("vehicle_down_payment"), min_value=0.0, max_value=vehicle_price,
                value=0.0, step=500.0, key="calc_auto_down",
            )
        requested_loan = vehicle_price - down_payment
        ltv_limit = vehicle_price * config.get("max_ltv", 1.20)
        asset_cap = min(requested_loan, ltv_limit)

    elif selected_key == "secured":
        st.markdown(f"##### {t('collateral_details')}")
        prop_type = st.selectbox(
            t("property_type"), options=t("property_types"), key="calc_prop_type",
        )
        if not prop_type:
            st.warning(t("property_required"))
            return
        collateral_value = st.number_input(
            t("collateral_value"), min_value=0.0, value=100000.0, step=5000.0,
            key="calc_collateral_value",
        )
        if collateral_value <= 0:
            st.warning(t("property_required"))
            return
        ltv_limit = collateral_value * config.get("max_ltv", 0.80)
        asset_cap = ltv_limit
        st.caption(f"{t('ltv_ratio')}: {config.get('max_ltv', 0.80) * 100:.0f}%")

    elif selected_key == "business":
        st.markdown(f"##### {t('business_details')}")
        annual_revenue = st.number_input(
            t("annual_revenue"), min_value=0.0, value=100000.0, step=10000.0,
            key="calc_annual_revenue",
        )
        if annual_revenue > 0:
            st.info(t("revenue_info").format(amount=f"{annual_revenue:,.0f}"))

    # ── Max loan amount ──
    max_new_payment = (gross_income * max_dti) - existing_debt
    max_by_dti = calculate_max_loan_amount(max_new_payment, annual_rate, term_months)
    type_max = config.get("max_amount", float("inf"))
    type_min = config.get("min_amount", 0)
    max_amount = min(max_by_dti, asset_cap, type_max)
    max_amount = max(0, round(max_amount, 2))

    render_metric_row([
        (t("annual_interest_rate"), f"{annual_rate * 100:.1f}%"),
        (t("max_loan_amount"), f"${max_amount:,.0f}"),
    ], highlight_idx=1)

    if max_amount < type_min:
        st.warning(t("below_min_amount").format(min=f"{type_min:,.0f}"))
        return

    st.success(t("eligible_badge"))

    # ── Amount slider ──
    slider_max = float(min(max_amount, type_max))
    slider_min = float(type_min)
    if slider_min >= slider_max:
        st.warning(t("below_min_amount").format(min=f"{type_min:,.0f}"))
        return
    slider_step = max(100.0, float(round(slider_max / 50, -2))) if slider_max > 5000 else 100.0
    default_value = round(slider_max * 0.5, -2)
    if selected_key in ("mortgage", "auto") and asset_cap < float("inf"):
        default_value = min(slider_max, asset_cap)
    default_value = float(min(slider_max, max(slider_min, default_value)))

    desired_amount = st.slider(
        t("desired_amount"), min_value=slider_min, max_value=slider_max,
        value=default_value, step=slider_step, key="calc_desired_amount",
    )

    # ── Loan summary ──
    monthly = calculate_monthly_payment(desired_amount, annual_rate, term_months)
    total_repayment = monthly * term_months
    total_interest = total_repayment - desired_amount
    new_dti = (existing_debt + monthly) / gross_income

    st.markdown(f"##### {t('loan_summary')}")
    render_metric_row([
        (t("monthly_payment"), f"${monthly:,.2f}"),
        (t("total_interest"), f"${total_interest:,.2f}"),
        (t("total_repayment"), f"${total_repayment:,.2f}"),
    ], highlight_idx=0)

    st.markdown(t("new_dti_label").format(dti=f"{new_dti:.1%}"), unsafe_allow_html=True)
    render_dti_bar(new_dti, max_dti)

    # ── Repayment schedule ──
    with st.expander(t("repayment_schedule")):
        schedule_df = generate_repayment_schedule(desired_amount, annual_rate, term_months)
        # Rename columns to translated labels
        display_df = schedule_df.rename(columns={
            "Month": t("schedule_month"),
            "Payment": t("schedule_payment"),
            "Principal": t("schedule_principal"),
            "Interest": t("schedule_interest"),
            "Remaining Balance": t("schedule_balance"),
        })
        st.dataframe(display_df, use_container_width=True, hide_index=True)

        csv = schedule_df.to_csv(index=False)
        st.download_button(
            label=t("download_schedule"), data=csv,
            file_name="repayment_schedule.csv", mime="text/csv",
        )
