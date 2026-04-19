"""Reusable Streamlit UI components.

Renders score cards, metric rows, DTI bars, product cards, health indicators,
data completeness badges, and SHAP explanation panels.  Minimises usage of
``unsafe_allow_html`` where Streamlit native widgets suffice.
"""

from __future__ import annotations
from html import escape as html_escape
import streamlit as st
from app.translations import t
from config.business_rules import RISK_TIERS, get_risk_tier, get_risk_level

# ═══════════════════════════════════════════════════════════════
# Global CSS (injected once via render_global_css)
# ═══════════════════════════════════════════════════════════════
_GLOBAL_CSS = """
<style>
    /* ── Global ── */
    .main-header {
        font-size: 2.5rem; font-weight: 800; text-align: center;
        margin-bottom: 0.2rem;
        background: linear-gradient(135deg, #1f77b4 0%, #2ecc71 100%);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    }
    .main-subtitle {
        text-align: center; color: #888; font-size: 1rem; margin-bottom: 2rem;
    }
    /* ── Score card ── */
    .score-card {
        padding: 2.5rem 2rem; border-radius: 16px; text-align: center;
        margin: 1rem auto; max-width: 480px;
        box-shadow: 0 4px 24px rgba(0,0,0,0.10);
    }
    .very-low-risk { background: linear-gradient(135deg, #d4edda 0%, #c3e6cb 100%); border: 2px solid #28a745; color: #155724; }
    .low-risk      { background: linear-gradient(135deg, #cce5ff 0%, #b8daff 100%); border: 2px solid #007bff; color: #004085; }
    .moderate-risk { background: linear-gradient(135deg, #fff3cd 0%, #ffeeba 100%); border: 2px solid #ffc107; color: #856404; }
    .high-risk     { background: linear-gradient(135deg, #f8d7da 0%, #f5c6cb 100%); border: 2px solid #dc3545; color: #721c24; }
    .score-number  { font-size: 4.5rem; font-weight: 900; line-height: 1.1; margin: 0.4rem 0; }
    .score-card h2 { margin-bottom: 0; font-size: 1.15rem; text-transform: uppercase; letter-spacing: 0.05em; opacity: 0.75; }
    .score-card h3 { font-size: 1.35rem; margin-top: 0.3rem; }
    /* ── Info box ── */
    .info-box {
        background: linear-gradient(135deg, #0d47a1 0%, #1565c0 100%);
        padding: 1rem 1.2rem; border-radius: 10px; border-left: 5px solid #42a5f5;
        margin: 1rem 0; color: #ffffff; font-size: 0.92rem; line-height: 1.5;
    }
    /* ── DTI gauge ── */
    .dti-bar-bg {
        background: #e9ecef; border-radius: 10px; height: 18px; width: 100%;
        overflow: hidden; margin: 0.4rem 0;
    }
    .dti-bar-fill { height: 100%; border-radius: 10px; transition: width 0.3s; }
    .dti-bar-fill.ok   { background: linear-gradient(90deg, #28a745, #5cb85c); }
    .dti-bar-fill.warn { background: linear-gradient(90deg, #ffc107, #ffb300); }
    .dti-bar-fill.over { background: linear-gradient(90deg, #dc3545, #c62828); }
    /* ── Customer card ── */
    .customer-card {
        background: #f8f9fa; border-radius: 12px; padding: 1.5rem;
        border: 1px solid #e0e0e0; margin: 0.5rem 0;
    }
    .customer-card .field { margin-bottom: 0.6rem; }
    .customer-card .field-label { font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.04em; color: #888; margin-bottom: 0.1rem; }
    .customer-card .field-value { font-size: 1.05rem; font-weight: 600; color: #212529; }
    /* ── Tier badges ── */
    .tier-badge {
        padding: 12px 8px; border-radius: 10px; text-align: center;
        font-size: 0.85rem; font-weight: 600;
    }
    /* ── Metric cards ── */
    .metric-row { display: flex; gap: 0.75rem; flex-wrap: wrap; margin: 0.75rem 0; }
    .metric-card {
        flex: 1; min-width: 130px; background: #f8f9fa; border-radius: 10px;
        padding: 0.9rem 1rem; text-align: center; border: 1px solid #e0e0e0;
    }
    .metric-card .metric-label { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.04em; color: #888; }
    .metric-card .metric-value { font-size: 1.3rem; font-weight: 700; color: #212529; margin-top: 0.15rem; }
    .metric-card.highlight { border-color: #1f77b4; background: rgba(31,119,180,0.04); }
    /* ── Product card ── */
    .product-card {
        border: 2px solid #e0e0e0; border-radius: 12px; padding: 1rem; text-align: center;
        transition: all 0.15s; margin-bottom: 0.5rem;
    }
    .product-card.eligible { border-color: #28a745; }
    .product-card.not-eligible { border-color: #e0e0e0; opacity: 0.6; }
    .product-card .card-icon { font-size: 1.8rem; margin-bottom: 0.3rem; }
    .product-card .card-title { font-weight: 700; font-size: 0.9rem; }
    .product-card .card-detail { font-size: 0.78rem; color: #666; margin-top: 0.2rem; }
    /* ── Explanation panel ── */
    .explanation-item {
        display: flex; justify-content: space-between; align-items: center;
        padding: 0.4rem 0; border-bottom: 1px solid #f0f0f0;
    }
    .explanation-item:last-child { border-bottom: none; }
    .explanation-feature { font-weight: 600; font-size: 0.88rem; }
    .explanation-direction { font-size: 0.82rem; padding: 0.15rem 0.5rem; border-radius: 1rem; }
    .dir-risk { background: #f8d7da; color: #721c24; }
    .dir-safe { background: #d4edda; color: #155724; }
    /* ── Completeness badge ── */
    .completeness-badge {
        display: inline-block; padding: 0.3rem 0.8rem; border-radius: 1rem;
        font-size: 0.82rem; font-weight: 600;
    }
    .completeness-full    { background: #d4edda; color: #155724; }
    .completeness-partial { background: #fff3cd; color: #856404; }
    .completeness-minimal { background: #f8d7da; color: #721c24; }
</style>
"""


def render_global_css() -> None:
    """Inject global CSS once per page."""
    st.markdown(_GLOBAL_CSS, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════
# Component renderers
# ═══════════════════════════════════════════════════════════════

def render_health_indicator(health: dict | None) -> None:
    """Render service health dot in the sidebar."""
    if health and health.get("status") == "ok":
        st.success(t("service_online"))
    elif health and health.get("status") == "degraded":
        st.warning(t("service_online"))
    else:
        st.error(t("service_offline"))
        st.caption(t("service_run_hint"))


def render_data_completeness_badge(completeness: dict) -> None:
    """Render a colored badge showing data coverage."""
    confidence = completeness.get("confidence", "minimal")
    months = completeness.get("months_available", 0)
    css_class = f"completeness-{confidence}"

    if confidence == "full":
        label = t("data_full").format(months=months)
    elif confidence == "partial":
        label = t("data_partial").format(months=months)
    else:
        label = t("data_minimal").format(months=months)

    st.markdown(
        f'<span class="completeness-badge {css_class}">{html_escape(label)}</span>',
        unsafe_allow_html=True,
    )


def render_score_card(evaluation: dict) -> None:
    """Render the credit score visual card."""
    score = evaluation.get("credit_score", 0)
    risk_level = evaluation.get("risk_level", "Unknown")
    probability = evaluation.get("default_probability", "N/A")

    risk_map = {
        "Very Low Risk": t("very_low_risk"),
        "Low Risk": t("low_risk"),
        "Moderate Risk": t("moderate_risk"),
        "High Risk": t("high_risk"),
    }
    display_risk = risk_map.get(risk_level, risk_level)

    style = get_risk_tier(score)
    css_class = style["css_class"]
    color = style["color"]

    st.markdown(f"""
    <div class="score-card {css_class}">
        <h2>{html_escape(t("your_credit_score"))}</h2>
        <div class="score-number" style="color: {color};">{html_escape(str(score))}</div>
        <h3>{html_escape(display_risk)}</h3>
        <p>{html_escape(t("default_probability"))}: {html_escape(str(probability))}%</p>
    </div>
    """, unsafe_allow_html=True)


def render_score_interpretation(score: int) -> None:
    """Render the 4-tier score interpretation badges."""
    risk_map = {
        "Very Low Risk": t("very_low_risk"),
        "Low Risk": t("low_risk"),
        "Moderate Risk": t("moderate_risk"),
        "High Risk": t("high_risk"),
    }
    st.markdown(f"### {t('score_interpretation')}")
    cols = st.columns(4)
    current_tier = get_risk_level(score)
    for col, tier in zip(cols, RISK_TIERS):
        tier_label = risk_map.get(tier["name"], tier["name"])
        border = (
            f"3px solid {tier['color']}" if tier["name"] == current_tier
            else f"1px solid {tier['bg']}"
        )
        with col:
            st.markdown(f"""
            <div class="tier-badge" style="background-color: {tier['bg']}; border: {border};">
                <strong>{tier['range']}</strong><br>{html_escape(tier_label)}
            </div>
            """, unsafe_allow_html=True)


def render_explanation_panel(explanations: list[dict]) -> None:
    """Render 'Why this score?' section with SHAP-based factors."""
    st.markdown(f"#### {t('why_this_score')}")
    if not explanations:
        st.caption(t("no_explanations"))
        return

    for exp in explanations:
        display_name = html_escape(exp.get("display_name") or exp.get("feature_name") or "")
        if not display_name:
            continue
        direction = exp.get("direction", "")
        if direction == "increases_risk":
            dir_label = t("increases_risk")
            dir_class = "dir-risk"
        else:
            dir_label = t("decreases_risk")
            dir_class = "dir-safe"

        st.markdown(f"""
        <div class="explanation-item">
            <span class="explanation-feature">{display_name}</span>
            <span class="explanation-direction {dir_class}">{html_escape(dir_label)}</span>
        </div>
        """, unsafe_allow_html=True)


def render_metric_row(items: list[tuple[str, str]], highlight_idx: int | None = None) -> None:
    """Render a styled row of metric cards."""
    cards = []
    for i, (label, value) in enumerate(items):
        hl = " highlight" if i == highlight_idx else ""
        cards.append(
            f'<div class="metric-card{hl}">'
            f'<div class="metric-label">{html_escape(label)}</div>'
            f'<div class="metric-value">{html_escape(value)}</div>'
            f'</div>'
        )
    st.markdown(f'<div class="metric-row">{"".join(cards)}</div>', unsafe_allow_html=True)


def render_dti_bar(current_dti: float, max_dti: float) -> None:
    """Render a visual DTI progress bar."""
    pct = min(current_dti / max_dti * 100, 100) if max_dti > 0 else 0
    cls = "ok" if pct < 70 else ("warn" if pct < 100 else "over")
    st.markdown(
        f'<div class="dti-bar-bg">'
        f'<div class="dti-bar-fill {cls}" style="width:{pct:.0f}%"></div>'
        f'</div>',
        unsafe_allow_html=True,
    )


_PRODUCT_ICONS = {
    "personal": "💳", "mortgage": "🏠", "auto": "🚗",
    "education": "🎓", "business": "📊", "secured": "🏦",
}


def render_product_card(product: dict) -> None:
    """Render a single product eligibility card."""
    ptype = product.get("product_type", "")
    eligible = product.get("eligible", False)
    icon = _PRODUCT_ICONS.get(ptype, "📄")
    name = t(f"credit_{ptype}")
    badge = t("eligible_badge") if eligible else t("not_eligible_badge")
    css_class = "eligible" if eligible else "not-eligible"
    rate = product.get("rate")
    rate_str = f"{rate * 100:.1f}%" if rate else "—"
    max_amt = product.get("max_amount", 0)

    st.markdown(f"""
    <div class="product-card {css_class}">
        <div class="card-icon">{icon}</div>
        <div class="card-title">{html_escape(name)}</div>
        <div class="card-detail">{badge}</div>
        <div class="card-detail">{t("rate_label")}: {rate_str} · {t("max_amount_label")}: ${max_amt:,}</div>
    </div>
    """, unsafe_allow_html=True)


def render_customer_card(customer_data: dict) -> None:
    """Render a styled customer info card."""
    full_name = f"{customer_data.get('FirstName', '')} {customer_data.get('MiddleName', '')} {customer_data.get('LastName', '')}".strip()
    dob_val = str(customer_data.get("DateOfBirth", "N/A"))[:10]
    reg_val = str(customer_data.get("DateRegistered", "N/A"))[:10]
    country_val = customer_data.get("Country", "N/A")
    dep_val = str(customer_data.get("NumberOfDependents", 0))
    cid_val = customer_data.get("CustomerID", "N/A")

    st.markdown(f"""
    <div class="customer-card">
        <div style="display:grid; grid-template-columns:1fr 1fr 1fr; gap:0.8rem;">
            <div class="field"><div class="field-label">{html_escape(t('customer_id_label'))}</div><div class="field-value">{html_escape(str(cid_val))}</div></div>
            <div class="field"><div class="field-label">{html_escape(t('full_name_label'))}</div><div class="field-value">{html_escape(full_name)}</div></div>
            <div class="field"><div class="field-label">{html_escape(t('dob_label'))}</div><div class="field-value">{html_escape(dob_val)}</div></div>
            <div class="field"><div class="field-label">{html_escape(t('date_registered_label'))}</div><div class="field-value">{html_escape(reg_val)}</div></div>
            <div class="field"><div class="field-label">{html_escape(t('country_label'))}</div><div class="field-value">{html_escape(str(country_val))}</div></div>
            <div class="field"><div class="field-label">{html_escape(t('dependents_label'))}</div><div class="field-value">{html_escape(dep_val)}</div></div>
        </div>
    </div>
    """, unsafe_allow_html=True)
