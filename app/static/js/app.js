/* app.js — Main application logic, state management, event binding. */

(() => {
    'use strict';

    // ── Utility ──
    function debounce(fn, ms) {
        let timer;
        return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), ms); };
    }

    // ── State ──
    let state = {
        customerFound: false,
        customerData: null,
        loanData: [],
        txnData: [],
        evaluationResult: null,
        isNewCustomer: false,
        businessRules: null,
    };

    // ── DOM refs (populated after DOMContentLoaded) ──
    let $;

    // ── Init ──
    document.addEventListener('DOMContentLoaded', async () => {
        $ = {
            langSelect: document.getElementById('language-select'),
            mainHeader: document.getElementById('main-header'),
            searchBtn: document.getElementById('search-btn'),
            firstName: document.getElementById('first-name-select'),
            lastName: document.getElementById('last-name-select'),
            firstNameDropdown: document.getElementById('first-name-dropdown'),
            lastNameDropdown: document.getElementById('last-name-dropdown'),
            searchResult: document.getElementById('search-result'),
            modeExistingBtn: document.getElementById('mode-existing-btn'),
            modeNewBtn: document.getElementById('mode-new-btn'),
            clearCustomerBtn: document.getElementById('clear-customer-btn'),
            existingSection: document.getElementById('existing-customer-section'),
            newSection: document.getElementById('new-customer-section'),
            customerInfoCard: document.getElementById('customer-info-card'),
            loansTbody: document.getElementById('loans-tbody'),
            txnsTbody: document.getElementById('txns-tbody'),
            addLoanBtn: document.getElementById('add-loan-btn'),
            addTxnBtn: document.getElementById('add-txn-btn'),
            evaluateBtn: document.getElementById('evaluate-btn'),
            saveDraftBtn: document.getElementById('save-draft-btn'),
            resetBtn: document.getElementById('reset-btn'),
            feedback: document.getElementById('action-feedback'),
            resultsPlaceholder: document.getElementById('results-placeholder'),
            resultsContent: document.getElementById('results-content'),
            scoreCard: document.getElementById('score-card'),
            dataCompleteness: document.getElementById('data-completeness'),
            scoreInterpBody: document.getElementById('score-interpretation-body'),
            explanationsPanel: document.getElementById('explanations-panel'),
            affordabilityPanel: document.getElementById('affordability-panel'),
            productsPanel: document.getElementById('products-panel'),
            calculatorPanel: document.getElementById('calculator-panel'),
            healthDot: document.querySelector('.health-dot'),
            healthText: document.getElementById('health-text'),
        };

        // Load translations + business rules in parallel
        await Promise.all([I18n.load(), loadBusinessRules()]);

        // Set language from storage
        $.langSelect.value = I18n.lang();

        // Translate UI
        translateUI();

        // Load name dropdowns
        await loadNameLists();

        // Health check
        checkHealth();
        setInterval(checkHealth, 10000);

        // ── Event Listeners ──
        $.langSelect.addEventListener('change', onLanguageChange);
        $.modeExistingBtn.addEventListener('click', () => switchMode('existing'));
        $.modeNewBtn.addEventListener('click', () => switchMode('new'));
        $.clearCustomerBtn.addEventListener('click', clearCustomerSelection);
        $.searchBtn.addEventListener('click', onSearch);
        $.addLoanBtn.addEventListener('click', () => { $.loansTbody.insertAdjacentHTML('beforeend', Components.loanRow()); });
        $.addTxnBtn.addEventListener('click', () => { $.txnsTbody.insertAdjacentHTML('beforeend', Components.txnRow()); });
        $.evaluateBtn.addEventListener('click', onEvaluate);
        $.saveDraftBtn.addEventListener('click', onSaveDraft);
        $.resetBtn.addEventListener('click', onReset);

        // Helper: trigger search whenever both names are filled
        function tryAutoSearch() {
            const f = $.firstName.value.trim();
            const l = $.lastName.value.trim();
            if (f && l) onSearch();
        }

        // Autocomplete for name fields with cross-filter + auto-search callbacks
        setupAutocomplete($.lastName, $.lastNameDropdown, 'lastNames', async (val) => {
            try {
                _nameLists.firstNames = await API.getFirstNames(val);
                if (_nameLists.firstNames.length === 1) {
                    $.firstName.value = _nameLists.firstNames[0];
                    $.firstName.dispatchEvent(new Event('change'));
                }
            } catch (e) { /* filter error, ignore */ }
            tryAutoSearch();
        });
        setupAutocomplete($.firstName, $.firstNameDropdown, 'firstNames', async (val) => {
            try {
                _nameLists.lastNames = await API.getLastNames(val);
                if (_nameLists.lastNames.length === 1) {
                    $.lastName.value = _nameLists.lastNames[0];
                    $.lastName.dispatchEvent(new Event('change'));
                }
            } catch (e) { /* filter error, ignore */ }
            tryAutoSearch();
        });

        // Auto-search whenever both names are filled — covers typing, pasting, tabbing away
        const autoSearch = debounce(tryAutoSearch, 400);
        for (const el of [$.firstName, $.lastName]) {
            el.addEventListener('input', autoSearch);
            el.addEventListener('change', autoSearch);
            el.addEventListener('blur', autoSearch);
        }

        // Enter key triggers search immediately
        $.firstName.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); onSearch(); }});
        $.lastName.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); onSearch(); }});

        // Auto-re-evaluate when financial data changes (edit, add row, remove row)
        const debouncedEvaluate = debounce(() => {
            if (state.customerFound || state.isNewCustomer) onEvaluate();
        }, 800);
        $.loansTbody.addEventListener('input', debouncedEvaluate);
        $.loansTbody.addEventListener('change', debouncedEvaluate);
        $.txnsTbody.addEventListener('input', debouncedEvaluate);
        $.txnsTbody.addEventListener('change', debouncedEvaluate);

        // Delegate remove-row clicks
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('remove-row-btn')) {
                e.target.closest('tr').remove();
                debouncedEvaluate();
            }
        });
    });

    // ── Load business rules ──
    async function loadBusinessRules() {
        state.businessRules = await API.getBusinessRules();
    }

    // ── Health check ──
    async function checkHealth() {
        const h = await API.checkHealth();
        const dot = $.healthDot;
        const txt = $.healthText;
        if (h.status === 'ok') {
            dot.className = 'health-dot online';
            txt.textContent = I18n.t('service_online');
        } else if (h.status === 'degraded') {
            dot.className = 'health-dot degraded';
            txt.textContent = I18n.t('service_degraded');
        } else {
            dot.className = 'health-dot offline';
            txt.textContent = I18n.t('service_offline');
        }
    }

    // ── Name lists ──
    const _nameLists = { firstNames: [], lastNames: [] };
    const MAX_DROPDOWN_ITEMS = 15;

    async function loadNameLists() {
        const [firstNames, lastNames] = await Promise.all([API.getFirstNames(), API.getLastNames()]);
        _nameLists.firstNames = firstNames;
        _nameLists.lastNames = lastNames;
    }

    function setupAutocomplete(input, dropdown, listKey, onSelect) {
        let activeIdx = -1;

        function showDropdown(query) {
            const items = _nameLists[listKey] || [];
            const q = query.toLowerCase();
            const filtered = q ? items.filter(n => n.toLowerCase().includes(q)).slice(0, MAX_DROPDOWN_ITEMS)
                               : items;
            if (filtered.length === 0) {
                dropdown.innerHTML = '<div class="ac-no-match">No matches</div>';
                dropdown.classList.remove('d-none');
                activeIdx = -1;
                return;
            }
            dropdown.innerHTML = filtered.map((n, i) =>
                `<div class="ac-item" data-idx="${i}" data-value="${Components.escapeHtml(n)}">${highlightMatch(n, q)}</div>`
            ).join('');
            dropdown.classList.remove('d-none');
            activeIdx = -1;
        }

        function highlightMatch(name, q) {
            if (!q) return Components.escapeHtml(name);
            const idx = name.toLowerCase().indexOf(q);
            if (idx < 0) return Components.escapeHtml(name);
            return Components.escapeHtml(name.substring(0, idx))
                + '<strong>' + Components.escapeHtml(name.substring(idx, idx + q.length)) + '</strong>'
                + Components.escapeHtml(name.substring(idx + q.length));
        }

        function selectItem(value) {
            input.value = value;
            dropdown.classList.add('d-none');
            if (onSelect) onSelect(value);
        }

        input.addEventListener('focus', () => showDropdown(input.value));
        input.addEventListener('input', () => showDropdown(input.value));

        dropdown.addEventListener('mousedown', (e) => {
            const item = e.target.closest('.ac-item');
            if (item) { e.preventDefault(); selectItem(item.dataset.value); }
        });

        input.addEventListener('blur', () => {
            setTimeout(() => dropdown.classList.add('d-none'), 150);
        });

        input.addEventListener('keydown', (e) => {
            const items = dropdown.querySelectorAll('.ac-item');
            if (!items.length) return;
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                activeIdx = Math.min(activeIdx + 1, items.length - 1);
                items.forEach((it, i) => it.classList.toggle('active', i === activeIdx));
                items[activeIdx]?.scrollIntoView({ block: 'nearest' });
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                activeIdx = Math.max(activeIdx - 1, 0);
                items.forEach((it, i) => it.classList.toggle('active', i === activeIdx));
                items[activeIdx]?.scrollIntoView({ block: 'nearest' });
            } else if (e.key === 'Enter' && activeIdx >= 0) {
                e.preventDefault();
                selectItem(items[activeIdx].dataset.value);
            } else if (e.key === 'Escape') {
                dropdown.classList.add('d-none');
            }
        });
    }

    // ── Language change ──
    async function onLanguageChange() {
        I18n.setLang($.langSelect.value);
        translateUI();
        // Re-render loan/txn dropdowns in new language
        rerenderEditorDropdowns();
        // Re-render results if present
        if (state.evaluationResult) renderResults(state.evaluationResult);
    }

    // ── Translate all static UI text ──
    function translateUI() {
        const t = I18n.t;
        $.mainHeader.textContent = t('main_header');
        setText('step1-header', '👤 ' + t('step1'));
        setText('mode-existing-label', t('search_btn').replace('🔍 ', '') || 'Find Existing');
        setText('mode-new-label', t('new_customer_toggle') || 'New Customer');
        setText('last-name-label', t('last_name'));
        setText('first-name-label', t('first_name'));
        document.querySelector('.search-btn-text').textContent = t('search_btn');
        setText('new-first-label', t('first_name_input'));
        setText('new-last-label', t('last_name_input'));
        setText('new-middle-label', t('middle_name'));
        setText('new-dob-label', t('dob'));
        setText('new-registered-label', t('date_registered_input'));
        setText('new-country-label', t('country_input'));
        setText('new-dependents-label', t('dependents_input'));
        setText('financial-history-header', t('financial_history'));
        setText('loans-tab-btn', t('loans_tab'));
        setText('txns-tab-btn', t('transactions_tab'));
        setText('loan-date-th', t('loan_date'));
        setText('loan-amount-th', t('amount'));
        setText('loan-emis-th', t('num_emis'));
        setText('loan-status-th', t('status'));
        setText('txn-date-th', t('date_col').replace(/\*/g, ''));
        setText('txn-amount-th', t('amount'));
        setText('txn-type-th', t('type_col').replace(/\*/g, ''));
        document.getElementById('evaluate-btn').textContent = t('evaluate_btn');
        document.getElementById('save-draft-btn').textContent = t('save_draft_btn');
        document.getElementById('reset-btn').textContent = t('reset_btn');
        setText('results-placeholder-text', t('results_placeholder'));
        setText('sidebar-service-status', t('service_status').replace(/\*/g, ''));
        setText('sidebar-help-header', t('help_header'));
        setText('sidebar-how-to-use', t('how_to_use'));
        const helpSteps = document.getElementById('sidebar-help-steps');
        if (helpSteps) helpSteps.innerHTML = markdownToHtml(t('help_steps'));
        setText('sidebar-understanding-score', t('understanding_score'));
        setText('tier-vlr', t('very_low_risk'));
        setText('tier-lr', t('low_risk'));
        setText('tier-mr', t('moderate_risk'));
        setText('tier-hr', t('high_risk'));
        setText('why-header', t('why_this_score'));
        setText('affordability-header', t('affordability'));
        setText('products-header', t('product_cards_header'));
        setText('calculator-header', t('loan_calculator'));
        const ft = document.getElementById('footer-tip');
        if (ft) ft.innerHTML = t('footer_tip');
        const fs = document.getElementById('footer-security');
        if (fs) fs.innerHTML = t('footer_security');
    }

    function setText(id, text) {
        const el = document.getElementById(id);
        if (el) el.textContent = text;
    }

    function markdownToHtml(md) {
        if (!md) return '';
        return md.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>').replace(/\n/g, '<br>');
    }

    // ── Mode switching (existing / new) ──
    function switchMode(mode) {
        state.isNewCustomer = mode === 'new';
        $.modeExistingBtn.classList.toggle('active', mode === 'existing');
        $.modeNewBtn.classList.toggle('active', mode === 'new');
        $.existingSection.classList.toggle('d-none', mode === 'new');
        $.newSection.classList.toggle('d-none', mode === 'existing');
        if (mode === 'new') $.newSection.classList.add('fade-section');
        else $.existingSection.classList.add('fade-section');
        $.customerInfoCard.classList.add('d-none');
        $.searchResult.innerHTML = '';
        $.clearCustomerBtn.classList.add('d-none');
        _lastSearchKey = '';
        state.customerFound = false;
        state.customerData = null;
    }

    function clearCustomerSelection() {
        _lastSearchKey = '';
        state.customerFound = false;
        state.customerData = null;
        state.loanData = [];
        state.txnData = [];
        $.customerInfoCard.classList.add('d-none');
        $.searchResult.innerHTML = '';
        $.clearCustomerBtn.classList.add('d-none');
        $.firstName.value = '';
        $.lastName.value = '';
        $.loansTbody.innerHTML = '';
        $.txnsTbody.innerHTML = '';
        // Reset name lists to full
        loadNameLists();
    }

    // ── Search ──
    let _lastSearchKey = '';
    async function onSearch() {
        const first = $.firstName.value.trim();
        const last = $.lastName.value.trim();
        if (!first || !last) return;

        // Skip if same search already completed
        const key = first.toLowerCase() + '|' + last.toLowerCase();
        if (key === _lastSearchKey && state.customerFound) return;

        _lastSearchKey = key;
        Components.showSpinner();
        try {
            const data = await API.searchCustomers(first, last);
            const matches = data.matches || [];
            if (matches.length === 1) {
                selectCustomer(matches[0]);
                $.searchResult.innerHTML = `<div class="feedback-msg success">${Components.escapeHtml(I18n.t('welcome_back').replace('{name}', first))}</div>`;
            } else if (matches.length > 1) {
                showMultipleMatches(matches);
            } else {
                $.searchResult.innerHTML = `<div class="feedback-msg info">${Components.escapeHtml(I18n.t('new_customer'))}</div>`;
                state.customerFound = false;
            }
        } catch (e) {
            Components.feedback('action-feedback', e.message, 'error');
        } finally {
            Components.hideSpinner();
        }
    }

    function showMultipleMatches(matches) {
        const msg = I18n.t('multiple_matches').replace('{count}', matches.length);
        let html = `<div class="feedback-msg info mb-2">${Components.escapeHtml(msg)}</div>`;
        html += '<div class="match-cards">';
        for (const m of matches) {
            html += Components.renderMatchCard(m);
        }
        html += '</div>';
        $.searchResult.innerHTML = html;

        // Click on a match card to select
        $.searchResult.querySelectorAll('.match-card').forEach(card => {
            card.addEventListener('click', () => {
                const dob = card.dataset.dob;
                const match = matches.find(m => (m.DateOfBirth || '') === dob);
                if (match) selectCustomer(match);
            });
        });
    }

    async function selectCustomer(cust) {
        state.customerFound = true;
        state.customerData = cust;

        // Show customer card with animation
        $.customerInfoCard.innerHTML = Components.renderCustomerCard(cust);
        $.customerInfoCard.classList.remove('d-none');
        $.clearCustomerBtn.classList.remove('d-none');

        // Load loans & transactions
        Components.showSpinner();
        try {
            const cid = cust.CustomerID;
            const [loans, txns] = await Promise.all([API.getLoans(cid), API.getTransactions(cid)]);
            state.loanData = loans;
            state.txnData = txns;
            populateLoansTable(loans);
            populateTxnsTable(txns);
        } finally {
            Components.hideSpinner();
        }

        // Auto-evaluate after loading data
        onEvaluate();
    }

    // ── Populate editor tables ──
    function populateLoansTable(loans) {
        $.loansTbody.innerHTML = '';
        for (const loan of loans) {
            $.loansTbody.insertAdjacentHTML('beforeend', Components.loanRow(loan));
        }
    }

    function populateTxnsTable(txns) {
        $.txnsTbody.innerHTML = '';
        for (const txn of txns) {
            $.txnsTbody.insertAdjacentHTML('beforeend', Components.txnRow(txn));
        }
    }

    function rerenderEditorDropdowns() {
        // Re-render loan status and txn type dropdowns with new language
        const statuses = I18n.loanStatuses();
        document.querySelectorAll('.loan-status').forEach(sel => {
            const currentIdx = sel.selectedIndex;
            sel.innerHTML = statuses.map(s => `<option>${Components.escapeHtml(s)}</option>`).join('');
            if (currentIdx >= 0 && currentIdx < statuses.length) sel.selectedIndex = currentIdx;
        });
        const types = I18n.txnTypes();
        document.querySelectorAll('.txn-type').forEach(sel => {
            const currentIdx = sel.selectedIndex;
            sel.innerHTML = types.map(t => `<option>${Components.escapeHtml(t)}</option>`).join('');
            if (currentIdx >= 0 && currentIdx < types.length) sel.selectedIndex = currentIdx;
        });
    }

    // ── Collect form data ──
    function collectCustomerProfile() {
        if (state.isNewCustomer) {
            const firstName = document.getElementById('new-first-name').value.trim();
            const lastName = document.getElementById('new-last-name').value.trim();
            const dob = document.getElementById('new-dob').value;
            const dateRegistered = document.getElementById('new-date-registered').value || new Date().toISOString().slice(0, 10);
            const dependents = parseInt(document.getElementById('new-dependents').value) || 0;

            if (!firstName || !lastName) return null;
            if (dob && dob > new Date().toISOString().slice(0, 10)) return null;
            if (dateRegistered > new Date().toISOString().slice(0, 10)) return null;
            if (dependents < 0 || dependents > 20) return null;

            return {
                FirstName: firstName,
                LastName: lastName,
                MiddleName: document.getElementById('new-middle-name').value.trim(),
                DateOfBirth: dob,
                DateRegistered: dateRegistered,
                Country: document.getElementById('new-country').value.trim(),
                NumberOfDependents: dependents,
                Defaulted: 0,
            };
        }
        if (state.customerData) {
            return { ...state.customerData };
        }
        return null;
    }

    function collectLoans() {
        const rows = $.loansTbody.querySelectorAll('tr');
        const loans = [];
        rows.forEach(tr => {
            const date = tr.querySelector('.loan-date')?.value || '';
            const amount = parseFloat(tr.querySelector('.loan-amount')?.value);
            const emis = parseInt(tr.querySelector('.loan-emis')?.value);
            const statusDisplay = tr.querySelector('.loan-status')?.value;
            const status = I18n.mapLoanStatusToEnglish(statusDisplay);
            if (amount > 0 && emis > 0) {
                const loan = { Amount: amount, NumberOfEMIs: emis, LoanStatus: status };
                if (date) loan.LoanApplicationDate = date;
                loans.push(loan);
            }
        });
        return loans;
    }

    function collectTransactions() {
        const rows = $.txnsTbody.querySelectorAll('tr');
        const txns = [];
        rows.forEach(tr => {
            const date = tr.querySelector('.txn-date')?.value;
            const amount = parseFloat(tr.querySelector('.txn-amount')?.value);
            const typeDisplay = tr.querySelector('.txn-type')?.value;
            const type = I18n.mapTxnTypeToEnglish(typeDisplay);
            if (date && amount > 0) {
                txns.push({ TransactionDate: date, Amount: amount, Type: type });
            }
        });
        return txns;
    }

    // ── Evaluate ──
    async function onEvaluate() {
        const profile = collectCustomerProfile();
        if (!profile || !profile.FirstName || !profile.LastName) {
            Components.feedback('action-feedback', I18n.t('enter_both_names'), 'error');
            return;
        }
        if (state.isNewCustomer && !profile.DateOfBirth) {
            Components.feedback('action-feedback', I18n.t('dob') + ' is required', 'error');
            return;
        }

        const loans = collectLoans();
        const txns = collectTransactions();

        Components.showSpinner();
        let result;
        try {
            result = await API.evaluate(profile, loans, txns);
        } catch (e) {
            console.error('Evaluate API error:', e);
            Components.hideSpinner();
            if (e.status === 503) {
                Components.feedback('action-feedback', I18n.t('service_unavailable_msg'), 'error');
            } else if (e.status === 422) {
                Components.feedback('action-feedback', I18n.t('validation_error').replace('{details}', e.message), 'error');
            } else {
                Components.feedback('action-feedback', I18n.t('scoring_error'), 'error');
            }
            return;
        }
        try {
            state.evaluationResult = result;
            renderResults(result);
        } catch (renderErr) {
            console.error('Render error:', renderErr);
            Components.feedback('action-feedback', 'Display error: ' + renderErr.message, 'error');
        } finally {
            Components.hideSpinner();
        }
    }

    // ── Render Results ──
    function renderResults(result) {
        $.resultsPlaceholder.classList.add('d-none');
        $.resultsContent.classList.remove('d-none');

        // Score card
        $.scoreCard.innerHTML = Components.renderScoreCard(result);

        // Data completeness
        $.dataCompleteness.innerHTML = Components.renderCompleteness(result.data_completeness);

        // Score interpretation
        const tiers = state.businessRules ? state.businessRules.risk_tiers : [];
        $.scoreInterpBody.innerHTML = Components.renderScoreInterpretation(result.credit_score, tiers);

        // Explanations
        $.explanationsPanel.innerHTML = Components.renderExplanations(result.explanations);

        // Affordability
        const bmrc = result.bmrc != null ? result.bmrc.toFixed(2) : '0';
        const fmrc = result.fmrc != null ? result.fmrc.toFixed(2) : '0';
        $.affordabilityPanel.innerHTML = Components.renderMetricRow([
            { value: '$' + bmrc, label: 'BMRC' },
            { value: '$' + fmrc, label: 'FMRC' },
        ], 1) + `<div class="text-muted small mt-1">${Components.escapeHtml(I18n.t('monthly_cash_flow'))}</div>`;

        // Products
        $.productsPanel.innerHTML = Components.renderProductCards(result.eligible_products || []);

        // Loan Calculator
        renderLoanCalculator(result);
    }

    // ── Loan Calculator ──
    function renderLoanCalculator(result) {
        const eligible = (result.eligible_products || []).filter(p => p.eligible);
        if (eligible.length === 0) {
            $.calculatorPanel.innerHTML = `<p class="text-muted">${Components.escapeHtml(I18n.t('not_eligible_msg').replace('{reason}', ''))}</p>`;
            return;
        }

        const rules = state.businessRules ? state.businessRules.credit_types : {};
        const icons = { personal: '💳', mortgage: '🏠', auto: '🚗', education: '📚', business: '📊', secured: '🏦' };

        let html = '';

        // Product selector
        html += `<div class="calc-section">
            <label class="form-label">${Components.escapeHtml(I18n.t('select_credit_type'))}</label>
            <select id="calc-product" class="form-select form-select-sm">
                ${eligible.map(p => `<option value="${p.product_type}">${icons[p.product_type] || ''} ${Components.escapeHtml(I18n.t('credit_' + p.product_type))}</option>`).join('')}
            </select>
        </div>`;

        // Income section
        html += `<div class="calc-section">
            <h6>${Components.escapeHtml(I18n.t('income_section'))}</h6>`;
        if (result.fmrc) {
            html += `<div class="info-box mb-2">${I18n.t('fmrc_reference').replace('{amount}', result.fmrc.toFixed(0)).replace('**', '<strong>').replace('**', '</strong>')}</div>`;
        }
        html += `<div class="row g-2">
                <div class="col-md-6">
                    <label class="form-label small">${Components.escapeHtml(I18n.t('gross_income_input'))}</label>
                    <input type="number" id="calc-income" class="form-control form-control-sm" min="0" step="100" value="${result.fmrc ? Math.round(result.fmrc) : 5000}">
                </div>
            </div>`;

        // Existing debts
        html += `<div class="mt-2">
            <label class="form-label small">${Components.escapeHtml(I18n.t('total_existing_debt'))}</label>
            <div class="input-group input-group-sm">
                <span class="input-group-text">$</span>
                <input type="number" class="form-control form-control-sm calc-debt" id="debt-total" min="0" step="50" value="0">
            </div>
            <div class="form-text" style="font-size:.72rem">${Components.escapeHtml(I18n.t('existing_debt_info'))}</div>
        </div>
        </div>`;

        // Type-specific inputs
        html += `<div id="calc-type-specific" class="calc-section"></div>`;

        // Term
        html += `<div class="calc-section">
            <label class="form-label small">${Components.escapeHtml(I18n.t('loan_term_months'))}</label>
            <input type="range" id="calc-term" class="form-range" min="12" max="84" step="6" value="12">
            <div class="d-flex justify-content-between" style="font-size:.78rem">
                <span id="calc-term-min">12</span>
                <span id="calc-term-val">12 months</span>
                <span id="calc-term-max">84</span>
            </div>
        </div>`;

        // Desired loan amount
        html += `<div class="calc-section">
            <label class="form-label small">${Components.escapeHtml(I18n.t('desired_amount'))}</label>
            <input type="number" id="calc-desired-amount" class="form-control form-control-sm" min="0" step="1000" value="0">
            <div class="form-text" style="font-size:.72rem"><span id="calc-max-amount-hint"></span></div>
        </div>`;

        // Summary
        html += `<div id="calc-summary" class="calc-section"></div>`;

        // Repayment schedule
        html += `<details class="calc-section">
            <summary>${Components.escapeHtml(I18n.t('repayment_schedule'))}</summary>
            <div id="calc-schedule" class="schedule-table mt-2"></div>
            <button id="download-csv-btn" class="btn btn-sm btn-outline-primary mt-2">${Components.escapeHtml(I18n.t('download_schedule'))}</button>
        </details>`;

        $.calculatorPanel.innerHTML = html;

        // Bind calculator events
        const recalc = () => updateCalculation(result);
        document.getElementById('calc-product').addEventListener('change', () => { $.calculatorPanel._userEditedDesired = false; renderTypeSpecific(result); recalc(); });
        document.getElementById('calc-income').addEventListener('input', () => { $.calculatorPanel._userEditedDesired = false; recalc(); $.calculatorPanel._userEditedDesired = true; });
        document.getElementById('calc-term').addEventListener('input', () => {
            document.getElementById('calc-term-val').textContent = document.getElementById('calc-term').value + ' ' + (I18n.t('term_months_unit') || 'months');
            recalc();
        });
        document.querySelectorAll('.calc-debt').forEach(el => el.addEventListener('input', () => { $.calculatorPanel._userEditedDesired = false; recalc(); $.calculatorPanel._userEditedDesired = true; }));
        document.getElementById('calc-desired-amount').addEventListener('input', () => {
            $.calculatorPanel._userEditedDesired = true;
            recalc();
        });
        document.getElementById('download-csv-btn').addEventListener('click', onDownloadCSV);

        renderTypeSpecific(result);
        recalc();
        // Lock desired amount after initial auto-fill so term changes affect the payment
        $.calculatorPanel._userEditedDesired = true;
    }

    function renderTypeSpecific(result) {
        const productKey = document.getElementById('calc-product').value;
        const container = document.getElementById('calc-type-specific');
        const rules = state.businessRules ? state.businessRules.credit_types : {};
        const config = rules[productKey] || {};

        // Update term slider range and step
        const termSlider = document.getElementById('calc-term');
        termSlider.min = config.min_term_months || 12;
        termSlider.max = config.max_term_months || 84;
        // Use step=12 for long-term products, step=6 for others
        const maxTerm = parseInt(termSlider.max);
        termSlider.step = maxTerm > 120 ? 12 : 6;
        // Always start at minimum term
        termSlider.value = termSlider.min;
        document.getElementById('calc-term-min').textContent = termSlider.min;
        document.getElementById('calc-term-max').textContent = termSlider.max;
        document.getElementById('calc-term-val').textContent = termSlider.value + ' ' + (I18n.t('term_months_unit') || 'months');

        let html = '';
        if (productKey === 'mortgage') {
            const minDown = (config.min_down_pct || 0.05) * 100;
            html = `<h6>${Components.escapeHtml(I18n.t('mortgage_details'))}</h6>
                <div class="row g-2">
                    <div class="col-6"><label class="form-label small">${Components.escapeHtml(I18n.t('property_value_mortgage'))}</label>
                        <input type="number" id="calc-property-value" class="form-control form-control-sm calc-extra" min="0" step="1000" value="300000"></div>
                    <div class="col-6"><label class="form-label small">${Components.escapeHtml(I18n.t('down_payment_pct'))}</label>
                        <input type="range" id="calc-down-pct" class="form-range calc-extra" min="${minDown}" max="50" value="20">
                        <span id="calc-down-pct-val" class="small">20%</span></div>
                </div>`;
        } else if (productKey === 'auto') {
            html = `<h6>${Components.escapeHtml(I18n.t('auto_details'))}</h6>
                <div class="row g-2">
                    <div class="col-6"><label class="form-label small">${Components.escapeHtml(I18n.t('vehicle_price'))}</label>
                        <input type="number" id="calc-vehicle-price" class="form-control form-control-sm calc-extra" min="0" step="1000" value="30000"></div>
                    <div class="col-6"><label class="form-label small">${Components.escapeHtml(I18n.t('vehicle_down_payment'))}</label>
                        <input type="number" id="calc-vehicle-down" class="form-control form-control-sm calc-extra" min="0" step="500" value="5000"></div>
                </div>`;
        } else if (productKey === 'secured') {
            const propTypes = I18n.t('property_types') || ['Apartment', 'House', 'Commercial Property', 'Land'];
            html = `<h6>${Components.escapeHtml(I18n.t('collateral_details'))}</h6>
                <div class="row g-2">
                    <div class="col-6"><label class="form-label small">${Components.escapeHtml(I18n.t('property_type'))}</label>
                        <select id="calc-prop-type" class="form-select form-select-sm">${propTypes.map(t => `<option>${Components.escapeHtml(t)}</option>`).join('')}</select></div>
                    <div class="col-6"><label class="form-label small">${Components.escapeHtml(I18n.t('collateral_value'))}</label>
                        <input type="number" id="calc-collateral" class="form-control form-control-sm calc-extra" min="0" step="1000" value="100000"></div>
                </div>`;
        } else if (productKey === 'business') {
            html = `<h6>${Components.escapeHtml(I18n.t('business_details'))}</h6>
                <div class="row g-2">
                    <div class="col-6"><label class="form-label small">${Components.escapeHtml(I18n.t('annual_revenue'))}</label>
                        <input type="number" id="calc-revenue" class="form-control form-control-sm calc-extra" min="0" step="1000" value="100000"></div>
                </div>`;
        }

        container.innerHTML = html;

        // Bind extra inputs
        const recalc = () => updateCalculation(result);
        container.querySelectorAll('.calc-extra').forEach(el => el.addEventListener('input', recalc));

        if (productKey === 'mortgage') {
            document.getElementById('calc-down-pct')?.addEventListener('input', function() {
                document.getElementById('calc-down-pct-val').textContent = this.value + '%';
                recalc();
            });
        }
    }

    function updateCalculation(result) {
        const productKey = document.getElementById('calc-product').value;
        const rules = state.businessRules ? state.businessRules.credit_types : {};
        const config = rules[productKey] || {};
        const income = parseFloat(document.getElementById('calc-income').value) || 0;
        const termMonths = parseInt(document.getElementById('calc-term').value) || 36;

        // Total existing debt
        const existingDebt = parseFloat(document.getElementById('debt-total')?.value) || 0;

        const maxDTI = config.max_dti || 0.43;

        // Rate from evaluation result
        const productInfo = (result.eligible_products || []).find(p => p.product_type === productKey);
        const rate = productInfo ? productInfo.rate : 0.12;

        // Max from DTI
        let maxFromDTI = Calculator.maxAmountForDTI(income, existingDebt, maxDTI, rate, termMonths);

        // Asset cap
        let assetCap = config.max_amount || Infinity;
        if (productKey === 'mortgage') {
            const propVal = parseFloat(document.getElementById('calc-property-value')?.value) || 0;
            const downPct = parseFloat(document.getElementById('calc-down-pct')?.value) || 20;
            assetCap = propVal * (1 - downPct / 100);
        } else if (productKey === 'auto') {
            const vehPrice = parseFloat(document.getElementById('calc-vehicle-price')?.value) || 0;
            const vehDown = parseFloat(document.getElementById('calc-vehicle-down')?.value) || 0;
            assetCap = Math.max(0, vehPrice - vehDown);
        } else if (productKey === 'secured') {
            const collateral = parseFloat(document.getElementById('calc-collateral')?.value) || 0;
            const maxLTV = config.max_ltv || 0.8;
            assetCap = collateral * maxLTV;
        }

        const productMax = config.max_amount || Infinity;
        const productMin = config.min_amount || 0;
        let maxLoan = Math.min(maxFromDTI, assetCap, productMax);
        maxLoan = Math.max(0, maxLoan);

        // Update max amount hint
        const hintEl = document.getElementById('calc-max-amount-hint');
        if (hintEl) hintEl.textContent = I18n.t('max_loan_amount') + ': ' + Components.fmt$(Math.round(maxLoan));

        // Use desired amount if user entered one, otherwise track max
        const desiredInput = document.getElementById('calc-desired-amount');
        if (desiredInput) desiredInput.max = Math.round(maxLoan);
        const userEdited = $.calculatorPanel._userEditedDesired;
        let desiredVal = parseFloat(desiredInput?.value) || 0;
        if (!userEdited || desiredVal <= 0) {
            desiredVal = maxLoan;
            if (desiredInput) desiredInput.value = Math.round(maxLoan);
        } else if (desiredVal > maxLoan) {
            desiredVal = maxLoan;
            if (desiredInput) desiredInput.value = Math.round(maxLoan);
        }
        const loanAmount = desiredVal;

        if (loanAmount <= 0) {
            document.getElementById('calc-summary').innerHTML =
                `<div class="feedback-msg info">${Components.escapeHtml(I18n.t('dti_too_high').replace('{dti:.1%}', (Calculator.dti(existingDebt, income)*100).toFixed(1)+'%').replace('{max_dti:.0%}', (maxDTI*100).toFixed(0)+'%'))}</div>`;
            document.getElementById('calc-schedule').innerHTML = '';
            return;
        }

        if (loanAmount < productMin) {
            document.getElementById('calc-summary').innerHTML =
                `<div class="feedback-msg info">${Components.escapeHtml(I18n.t('below_min_amount').replace('${min}', Components.fmt$(productMin)))}</div>`;
            document.getElementById('calc-schedule').innerHTML = '';
            return;
        }

        const monthlyPmt = Calculator.monthlyPayment(loanAmount, rate, termMonths);
        const totalRepayment = monthlyPmt * termMonths;
        const totalInterest = totalRepayment - loanAmount;
        const newDTI = Calculator.dti(existingDebt + monthlyPmt, income);

        let summaryHtml = `<h6>${Components.escapeHtml(I18n.t('loan_summary'))}</h6>`;
        summaryHtml += Components.renderMetricRow([
            { value: Components.fmt$(loanAmount), label: I18n.t('max_loan_amount') },
            { value: Components.fmt$(Math.round(monthlyPmt)), label: I18n.t('monthly_payment') },
            { value: Components.fmt$(Math.round(totalInterest)), label: I18n.t('total_interest') },
            { value: Components.fmt$(Math.round(totalRepayment)), label: I18n.t('total_repayment') },
        ], 1);

        summaryHtml += `<div class="mt-2 small">${Components.escapeHtml(I18n.t('annual_interest_rate'))}: <strong>${Components.fmtPct(rate)}</strong></div>`;
        summaryHtml += `<div class="mt-2">${Components.escapeHtml(I18n.t('new_dti_label').replace('{dti}', (newDTI * 100).toFixed(1) + '%').replace('**', '').replace('**', ''))}</div>`;
        summaryHtml += `<div class="mt-1">${Components.renderDTIBar(newDTI, maxDTI)}</div>`;

        document.getElementById('calc-summary').innerHTML = summaryHtml;

        // Repayment schedule
        const schedule = Calculator.repaymentSchedule(loanAmount, rate, termMonths);
        let schedHtml = `<table class="table table-sm table-bordered"><thead><tr>
            <th>${Components.escapeHtml(I18n.t('schedule_month'))}</th>
            <th>${Components.escapeHtml(I18n.t('schedule_payment'))}</th>
            <th>${Components.escapeHtml(I18n.t('schedule_principal'))}</th>
            <th>${Components.escapeHtml(I18n.t('schedule_interest'))}</th>
            <th>${Components.escapeHtml(I18n.t('schedule_balance'))}</th>
        </tr></thead><tbody>`;
        for (const row of schedule) {
            schedHtml += `<tr><td>${row.month}</td><td>${Components.fmt$(row.payment)}</td><td>${Components.fmt$(row.principal)}</td><td>${Components.fmt$(row.interest)}</td><td>${Components.fmt$(row.balance)}</td></tr>`;
        }
        schedHtml += '</tbody></table>';
        document.getElementById('calc-schedule').innerHTML = schedHtml;

        // Store schedule for CSV download
        $.calculatorPanel._lastSchedule = schedule;
    }

    function onDownloadCSV() {
        const schedule = $.calculatorPanel._lastSchedule;
        if (!schedule || schedule.length === 0) return;
        const csv = Calculator.scheduleToCSV(schedule);
        const blob = new Blob([csv], { type: 'text/csv' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'repayment_schedule.csv';
        a.click();
        URL.revokeObjectURL(url);
    }

    // ── Save Draft ──
    async function onSaveDraft() {
        const profile = collectCustomerProfile();
        if (!profile || !profile.FirstName || !profile.LastName) {
            Components.feedback('action-feedback', I18n.t('names_required'), 'error');
            return;
        }
        if (!profile.DateOfBirth) {
            Components.feedback('action-feedback', I18n.t('dob') + ' is required', 'error');
            return;
        }

        Components.showSpinner();
        try {
            const result = await API.saveCustomer(profile);
            const cid = result.CustomerID;

            const loans = collectLoans();
            const txns = collectTransactions();

            if (loans.length > 0) await API.saveLoans(cid, loans);
            if (txns.length > 0) await API.saveTransactions(cid, txns);

            Components.feedback('action-feedback', I18n.t('saved_msg').replace('{cid}', cid), 'success');
        } catch (e) {
            Components.feedback('action-feedback', I18n.t('save_error').replace('{err}', e.message), 'error');
        } finally {
            Components.hideSpinner();
        }
    }

    // ── Reset ──
    function onReset() {
        state = {
            customerFound: false,
            customerData: null,
            loanData: [],
            txnData: [],
            evaluationResult: null,
            isNewCustomer: false,
            businessRules: state.businessRules,
        };

        $.firstName.value = '';
        $.lastName.value = '';
        $.searchResult.innerHTML = '';
        $.customerInfoCard.classList.add('d-none');
        $.customerInfoCard.innerHTML = '';
        $.clearCustomerBtn.classList.add('d-none');
        $.loansTbody.innerHTML = '';
        $.txnsTbody.innerHTML = '';
        switchMode('existing');
        $.resultsPlaceholder.classList.remove('d-none');
        $.resultsContent.classList.add('d-none');

        // Clear new customer form
        ['new-first-name', 'new-last-name', 'new-middle-name', 'new-dob', 'new-date-registered', 'new-country'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.value = '';
        });
        const depEl = document.getElementById('new-dependents');
        if (depEl) depEl.value = '0';

        // Reset name lists
        loadNameLists();
    }

})();
