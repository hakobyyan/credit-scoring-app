/* api.js — REST API client for the Credit Scoring backend. */

const API = {
    async getFirstNames(lastName) {
        const params = lastName ? `?last_name=${encodeURIComponent(lastName)}` : '';
        const resp = await fetch(`/api/customers/first-names${params}`);
        if (!resp.ok) throw new Error(await resp.text());
        return resp.json();
    },

    async getLastNames(firstName) {
        const params = firstName ? `?first_name=${encodeURIComponent(firstName)}` : '';
        const resp = await fetch(`/api/customers/last-names${params}`);
        if (!resp.ok) throw new Error(await resp.text());
        return resp.json();
    },

    async searchCustomers(firstName, lastName, dob) {
        const body = { first_name: firstName, last_name: lastName };
        if (dob) body.dob = dob;
        const resp = await fetch('/api/customers/search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        if (!resp.ok) throw new Error(await resp.text());
        return resp.json();
    },

    async getLoans(customerId) {
        const resp = await fetch(`/api/customers/${encodeURIComponent(customerId)}/loans`);
        if (!resp.ok) throw new Error(await resp.text());
        return resp.json();
    },

    async getTransactions(customerId) {
        const resp = await fetch(`/api/customers/${encodeURIComponent(customerId)}/transactions`);
        if (!resp.ok) throw new Error(await resp.text());
        return resp.json();
    },

    async saveCustomer(profile) {
        const resp = await fetch('/api/customers', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(profile),
        });
        if (!resp.ok) throw new Error(await resp.text());
        return resp.json();
    },

    async saveLoans(customerId, loans) {
        const resp = await fetch(`/api/customers/${encodeURIComponent(customerId)}/loans`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(loans),
        });
        if (!resp.ok) throw new Error(await resp.text());
        return resp.json();
    },

    async saveTransactions(customerId, transactions) {
        const resp = await fetch(`/api/customers/${encodeURIComponent(customerId)}/transactions`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(transactions),
        });
        if (!resp.ok) throw new Error(await resp.text());
        return resp.json();
    },

    async evaluate(customerProfile, loanHistory, transactionHistory) {
        const resp = await fetch('/api/evaluate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                customer_profile: customerProfile,
                loan_history: loanHistory,
                transaction_history: transactionHistory,
            }),
        });
        if (!resp.ok) {
            const text = await resp.text();
            const err = new Error(text);
            err.status = resp.status;
            throw err;
        }
        return resp.json();
    },

    async checkHealth() {
        try {
            const resp = await fetch('/api/health');
            if (!resp.ok) return { status: 'offline', model_loaded: false };
            return resp.json();
        } catch {
            return { status: 'offline', model_loaded: false };
        }
    },

    async getTranslations() {
        const resp = await fetch('/api/translations');
        if (!resp.ok) throw new Error(await resp.text());
        return resp.json();
    },

    async getBusinessRules() {
        const resp = await fetch('/api/business-rules');
        if (!resp.ok) throw new Error(await resp.text());
        return resp.json();
    },
};
