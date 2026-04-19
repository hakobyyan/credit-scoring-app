/* translations.js — i18n system. Loads translations from the API. */

const I18n = (() => {
    let _translations = {};
    let _loanStatusMap = {};
    let _txnTypeMap = {};
    let _featureDisplayNamesI18n = {};
    let _currentLang = localStorage.getItem('app_language') || 'English';

    async function load() {
        const data = await API.getTranslations();
        _translations = data.translations || {};
        _loanStatusMap = data.loan_status_map || {};
        _txnTypeMap = data.txn_type_map || {};
        _featureDisplayNamesI18n = data.feature_display_names_i18n || {};
    }

    function lang() { return _currentLang; }

    function setLang(l) {
        _currentLang = l;
        localStorage.setItem('app_language', l);
    }

    function t(key) {
        const langDict = _translations[_currentLang] || _translations['English'] || {};
        const enDict = _translations['English'] || {};
        return langDict[key] !== undefined ? langDict[key] : (enDict[key] !== undefined ? enDict[key] : key);
    }

    function loanStatuses() {
        return t('loan_statuses') || ['Closed', 'Active', 'Defaulted'];
    }

    function txnTypes() {
        return t('txn_types') || ['Incoming', 'Outgoing'];
    }

    function mapLoanStatusToEnglish(displayVal) {
        const langMap = _loanStatusMap[_currentLang] || {};
        if (langMap[displayVal]) return langMap[displayVal];
        for (const m of Object.values(_loanStatusMap)) {
            if (m[displayVal]) return m[displayVal];
        }
        return displayVal;
    }

    function mapTxnTypeToEnglish(displayVal) {
        const langMap = _txnTypeMap[_currentLang] || {};
        if (langMap[displayVal]) return langMap[displayVal];
        for (const m of Object.values(_txnTypeMap)) {
            if (m[displayVal]) return m[displayVal];
        }
        return displayVal;
    }

    function featureName(englishName) {
        const langMap = _featureDisplayNamesI18n[_currentLang];
        if (langMap && langMap[englishName]) return langMap[englishName];
        return englishName;
    }

    return { load, lang, setLang, t, loanStatuses, txnTypes, mapLoanStatusToEnglish, mapTxnTypeToEnglish, featureName };
})();
