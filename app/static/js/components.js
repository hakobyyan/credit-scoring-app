/* components.js — Reusable UI rendering functions. */

const Components = (() => {

    function escapeHtml(str) {
        if (str == null) return '';
        return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
    }

    function fmt$(n) {
        if (n == null || isNaN(n)) return '$0';
        return '$' + Number(n).toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 });
    }

    function fmtPct(n, decimals = 1) {
        if (n == null || isNaN(n)) return '0%';
        return (n * 100).toFixed(decimals) + '%';
    }

    // ── Score Card ──
    function renderScoreCard(evaluation) {
        const score = evaluation.credit_score;
        const risk = evaluation.risk_level || '';
        const cssClass = risk.toLowerCase().replace(/\s+/g, '-');
        const prob = evaluation.default_probability;
        return `
            <div class="card-body p-0">
                <div class="score-card-inner ${escapeHtml(cssClass)}">
                    <div class="score-label">${escapeHtml(I18n.t('your_credit_score'))}</div>
                    <div class="score-number">${escapeHtml(score)}</div>
                    <div class="risk-badge">${escapeHtml(risk)}</div>
                </div>
                <div class="default-prob text-center mt-2 mb-2">
                    ${escapeHtml(I18n.t('default_probability'))}: <strong>${escapeHtml(prob)}%</strong>
                </div>
            </div>`;
    }

    // ── Data Completeness ──
    function renderCompleteness(dc) {
        if (!dc) return '';
        const months = dc.months_available;
        const conf = dc.confidence;
        let cls = 'completeness-minimal', textKey = 'data_minimal';
        if (conf === 'full') { cls = 'completeness-full'; textKey = 'data_full'; }
        else if (conf === 'partial') { cls = 'completeness-partial'; textKey = 'data_partial'; }
        const label = I18n.t('data_completeness');
        const text = I18n.t(textKey).replace('{months}', months);
        return `<div><strong>${escapeHtml(label)}:</strong> <span class="completeness-badge ${cls}">${escapeHtml(text)}</span></div>`;
    }

    // ── Score Interpretation ──
    function renderScoreInterpretation(score, riskTiers) {
        const tiers = [
            { key: 'very_low_risk', cls: 'interp-very-low', min: 751 },
            { key: 'low_risk', cls: 'interp-low', min: 651 },
            { key: 'moderate_risk', cls: 'interp-moderate', min: 551 },
            { key: 'high_risk', cls: 'interp-high', min: 0 },
        ];
        let html = `<h6>${escapeHtml(I18n.t('score_interpretation'))}</h6><div class="interp-badges">`;
        for (const t of tiers) {
            const active = score >= t.min && (t === tiers[0] || score < tiers[tiers.indexOf(t) - 1].min) ? ' active' : '';
            // simpler: check which tier the score lands in
            html += `<div class="interp-badge ${t.cls}${score >= t.min && (tiers.indexOf(t) === 0 || score < tiers[tiers.indexOf(t)-1].min) ? ' active' : ''}">${escapeHtml(I18n.t(t.key))}<br><small>${escapeHtml((riskTiers && riskTiers[tiers.indexOf(t)]) ? riskTiers[tiers.indexOf(t)].range : '')}</small></div>`;
        }
        html += '</div>';
        return html;
    }

    // ── SHAP Explanations ──
    function renderExplanations(explanations) {
        if (!explanations || explanations.length === 0) {
            return `<p class="text-muted">${escapeHtml(I18n.t('no_explanations'))}</p>`;
        }
        let html = '';
        const maxContrib = Math.max(...explanations.map(e => Math.abs(e.contribution)));
        for (const ex of explanations) {
            const pct = maxContrib > 0 ? (Math.abs(ex.contribution) / maxContrib * 100) : 0;
            const isRisk = ex.direction === 'increases_risk';
            const barCls = isRisk ? 'risk' : 'safe';
            const dirText = isRisk ? I18n.t('increases_risk') : I18n.t('decreases_risk');
            html += `<div class="explanation-item">
                <span class="explanation-name">${escapeHtml(I18n.featureName(ex.display_name || ex.feature_name))}</span>
                <div class="explanation-bar-wrap"><div class="explanation-bar ${barCls}" style="width:${pct}%"></div></div>
                <span class="explanation-dir">${escapeHtml(dirText)}</span>
            </div>`;
        }
        return html;
    }

    // ── Metric Row ──
    function renderMetricRow(items, highlightIdx) {
        let html = '<div class="metric-row">';
        items.forEach((item, i) => {
            const hl = i === highlightIdx ? ' highlight' : '';
            html += `<div class="metric-card${hl}">
                <div class="metric-value">${escapeHtml(item.value)}</div>
                <div class="metric-label">${escapeHtml(item.label)}</div>
            </div>`;
        });
        html += '</div>';
        return html;
    }

    // ── Product Cards ──
    function renderProductCards(products) {
        const icons = { personal: '💳', mortgage: '🏠', auto: '🚗', education: '📚', business: '📊', secured: '🏦' };
        let html = '<div class="product-grid">';
        const eligible = products.filter(p => p.eligible);
        const ineligible = products.filter(p => !p.eligible);

        for (const p of eligible) {
            const nameKey = 'credit_' + p.product_type;
            html += `<div class="product-card eligible">
                <div class="d-flex justify-content-between align-items-start">
                    <div><span class="product-icon">${icons[p.product_type] || '📋'}</span> <span class="product-name">${escapeHtml(I18n.t(nameKey))}</span></div>
                    <span class="product-badge ok">${escapeHtml(I18n.t('eligible_badge'))}</span>
                </div>
                <div class="product-detail mt-1">${escapeHtml(I18n.t('min_score_label'))}: ${p.min_score} · ${escapeHtml(I18n.t('rate_label'))}: ${fmtPct(p.rate)} · ${escapeHtml(I18n.t('max_amount_label'))}: ${fmt$(p.max_amount)}</div>
            </div>`;
        }
        if (ineligible.length > 0) {
            html += '</div><details class="mt-2"><summary class="text-muted small">' + escapeHtml(I18n.t('not_eligible_badge')) + ' (' + ineligible.length + ')</summary><div class="product-grid mt-2">';
            for (const p of ineligible) {
                const nameKey = 'credit_' + p.product_type;
                html += `<div class="product-card ineligible">
                    <div class="d-flex justify-content-between align-items-start">
                        <div><span class="product-icon">${icons[p.product_type] || '📋'}</span> <span class="product-name">${escapeHtml(I18n.t(nameKey))}</span></div>
                        <span class="product-badge no">${escapeHtml(I18n.t('not_eligible_badge'))}</span>
                    </div>
                    <div class="product-detail mt-1">${escapeHtml(I18n.t('min_score_label'))}: ${p.min_score}</div>
                </div>`;
            }
            html += '</div></details>';
        } else {
            html += '</div>';
        }
        return html;
    }

    // ── DTI Bar ──
    function renderDTIBar(currentDTI, maxDTI) {
        const pct = Math.min(currentDTI / (maxDTI * 1.3), 1) * 100;
        const limitPct = (maxDTI / (maxDTI * 1.3)) * 100;
        let cls = 'ok';
        if (currentDTI >= maxDTI) cls = 'over';
        else if (currentDTI >= maxDTI * 0.8) cls = 'warn';
        return `<div class="dti-bar-wrap">
            <div class="dti-bar ${cls}" style="width:${pct}%"></div>
            <div class="dti-limit-mark" style="left:${limitPct}%"></div>
        </div>
        <div class="d-flex justify-content-between mt-1" style="font-size:.78rem">
            <span>${escapeHtml(I18n.t('dti_ratio_label'))}: ${(currentDTI*100).toFixed(1)}%</span>
            <span>Max: ${(maxDTI*100).toFixed(0)}%</span>
        </div>`;
    }

    // ── Avatar color from name ──
    function avatarColor(name) {
        const colors = ['#4e79a7','#f28e2b','#e15759','#76b7b2','#59a14f','#edc948','#b07aa1','#ff9da7','#9c755f','#bab0ac'];
        let hash = 0;
        for (let i = 0; i < (name || '').length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash);
        return colors[Math.abs(hash) % colors.length];
    }

    function initials(data) {
        return ((data.FirstName || '')[0] || '') + ((data.LastName || '')[0] || '');
    }

    // ── Customer Info Card ──
    function renderCustomerCard(data) {
        const fullName = [data.FirstName, data.MiddleName, data.LastName].filter(Boolean).join(' ');
        const ini = initials(data);
        const bg = avatarColor(fullName);
        const lifecycle = (data.LifecycleStatus || 'new').toLowerCase();
        const lifecycleCls = ['active','dormant','closed'].includes(lifecycle) ? lifecycle : 'new';

        const details = [
            ['dob_label', data.DateOfBirth],
            ['date_registered_label', data.DateRegistered],
            ['country_label', data.Country],
            ['dependents_label', data.NumberOfDependents],
        ].filter(([, v]) => v != null && v !== '');

        let html = `<div class="customer-info-panel">
            <div class="d-flex align-items-center gap-3 mb-2">
                <div class="customer-avatar" style="background:${bg}">${escapeHtml(ini)}</div>
                <div class="flex-grow-1">
                    <div class="customer-name">${escapeHtml(fullName)}</div>
                    <div class="customer-id-text">${escapeHtml(data.CustomerID || I18n.t('new_customer'))}</div>
                </div>
                <span class="lifecycle-badge ${lifecycleCls}">${escapeHtml(data.LifecycleStatus || 'New')}</span>
            </div>
            <div class="customer-details-grid">`;
        for (const [key, val] of details) {
            html += `<div class="customer-detail-item"><div class="detail-label">${escapeHtml(I18n.t(key))}</div><div class="detail-value">${escapeHtml(String(val))}</div></div>`;
        }
        html += '</div></div>';
        return html;
    }

    // ── Match card for disambiguation ──
    function renderMatchCard(data) {
        const fullName = [data.FirstName, data.MiddleName, data.LastName].filter(Boolean).join(' ');
        const ini = initials(data);
        const bg = avatarColor(fullName);
        const meta = [data.DateOfBirth, data.Country].filter(Boolean).join(' · ');
        return `<div class="match-card" data-dob="${escapeHtml(data.DateOfBirth || '')}">
            <div class="match-avatar" style="background:${bg}">${escapeHtml(ini)}</div>
            <div class="match-info">
                <div class="match-name">${escapeHtml(fullName)}</div>
                <div class="match-meta">${escapeHtml(meta)}</div>
            </div>
        </div>`;
    }

    // ── Loan Editor Row ──
    function loanRow(loan) {
        const statuses = I18n.loanStatuses();
        const d = loan || {};
        let opts = statuses.map(s => `<option${d.LoanStatus === s || d.Status === s ? ' selected' : ''}>${escapeHtml(s)}</option>`).join('');
        return `<tr>
            <td><input type="date" class="form-control form-control-sm loan-date" value="${escapeHtml(d.LoanApplicationDate || d.LoanDate || '')}"></td>
            <td><input type="number" class="form-control form-control-sm loan-amount" min="0" step="100" value="${d.Amount || ''}"></td>
            <td><input type="number" class="form-control form-control-sm loan-emis" min="1" value="${d.NumberOfEMIs || d.EMIs || ''}"></td>
            <td><select class="form-select form-select-sm loan-status">${opts}</select></td>
            <td><button class="btn btn-sm btn-outline-danger remove-row-btn">&times;</button></td>
        </tr>`;
    }

    // ── Transaction Editor Row ──
    function txnRow(txn) {
        const types = I18n.txnTypes();
        const d = txn || {};
        let opts = types.map(t => `<option${d.Type === t ? ' selected' : ''}>${escapeHtml(t)}</option>`).join('');
        return `<tr>
            <td><input type="date" class="form-control form-control-sm txn-date" value="${escapeHtml(d.TransactionDate || d.Date || '')}"></td>
            <td><input type="number" class="form-control form-control-sm txn-amount" min="0" step="10" value="${d.Amount || ''}"></td>
            <td><select class="form-select form-select-sm txn-type">${opts}</select></td>
            <td><button class="btn btn-sm btn-outline-danger remove-row-btn">&times;</button></td>
        </tr>`;
    }

    // ── Spinner ──
    function showSpinner() {
        if (!document.getElementById('spinner-overlay')) {
            document.body.insertAdjacentHTML('beforeend', '<div id="spinner-overlay" class="spinner-overlay"><div class="spinner-border text-light" role="status"></div></div>');
        }
    }
    function hideSpinner() {
        const el = document.getElementById('spinner-overlay');
        if (el) el.remove();
    }

    // ── Feedback ──
    function feedback(containerId, msg, type) {
        const el = document.getElementById(containerId);
        if (!el) return;
        el.innerHTML = `<div class="feedback-msg ${type}">${escapeHtml(msg)}</div>`;
        setTimeout(() => { el.innerHTML = ''; }, 6000);
    }

    return {
        escapeHtml, fmt$, fmtPct,
        renderScoreCard, renderCompleteness, renderScoreInterpretation,
        renderExplanations, renderMetricRow, renderProductCards,
        renderDTIBar, renderCustomerCard, renderMatchCard,
        loanRow, txnRow,
        showSpinner, hideSpinner, feedback,
    };
})();
