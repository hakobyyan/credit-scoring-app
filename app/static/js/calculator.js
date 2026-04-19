/* calculator.js — Loan calculation logic (ported from domain.py). */

const Calculator = (() => {

    function monthlyPayment(principal, annualRate, termMonths) {
        if (principal <= 0 || termMonths <= 0 || annualRate < 0) return 0;
        const r = annualRate / 12;
        if (r === 0) return principal / termMonths;
        return principal * r * Math.pow(1 + r, termMonths) / (Math.pow(1 + r, termMonths) - 1);
    }

    function maxLoanAmount(maxMonthly, annualRate, termMonths) {
        if (maxMonthly <= 0 || annualRate <= 0 || termMonths <= 0) return 0;
        const r = annualRate / 12;
        return Math.max(0, Math.round(maxMonthly * ((1 - Math.pow(1 + r, -termMonths)) / r) * 100) / 100);
    }

    function dti(totalMonthlyDebt, grossMonthlyIncome) {
        if (grossMonthlyIncome <= 0) return 0;
        return totalMonthlyDebt / grossMonthlyIncome;
    }

    function maxAmountForDTI(grossIncome, existingDebt, maxDTI, annualRate, termMonths) {
        const maxNewPayment = (grossIncome * maxDTI) - existingDebt;
        if (maxNewPayment <= 0) return 0;
        return maxLoanAmount(maxNewPayment, annualRate, termMonths);
    }

    function repaymentSchedule(principal, annualRate, termMonths) {
        const r = annualRate / 12;
        const pmt = monthlyPayment(principal, annualRate, termMonths);
        const schedule = [];
        let balance = principal;
        for (let month = 1; month <= termMonths; month++) {
            const interest = balance * r;
            const principalPmt = pmt - interest;
            balance = Math.max(0, balance - principalPmt);
            schedule.push({
                month,
                payment: Math.round(pmt * 100) / 100,
                principal: Math.round(principalPmt * 100) / 100,
                interest: Math.round(interest * 100) / 100,
                balance: Math.round(balance * 100) / 100,
            });
        }
        return schedule;
    }

    function scheduleToCSV(schedule) {
        const header = 'Month,Payment,Principal,Interest,Remaining Balance\n';
        const rows = schedule.map(r => `${r.month},${r.payment},${r.principal},${r.interest},${r.balance}`);
        return header + rows.join('\n');
    }

    return { monthlyPayment, maxLoanAmount, dti, maxAmountForDTI, repaymentSchedule, scheduleToCSV };
})();
