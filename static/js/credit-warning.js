(function () {
    'use strict';

    var dataElement = document.getElementById('credit-warning-data');
    if (!dataElement) return;
    var customers = JSON.parse(dataElement.textContent);

    function cents(value) {
        var match = String(value || '').trim().replace(',', '.').match(/^(\d+)(?:\.(\d{0,2}))?$/);
        return match ? Number(match[1]) * 100 + Number((match[2] || '').padEnd(2, '0')) : null;
    }

    document.querySelectorAll('[data-credit-warning]').forEach(function (form) {
        var customer = document.getElementById(form.dataset.customer);
        var amount = document.getElementById(form.dataset.amount);
        var method = form.dataset.method ? document.getElementById(form.dataset.method) : null;
        var warning = document.getElementById(form.dataset.creditWarning);
        if (!customer || !amount || !warning) return;

        function update() {
            var data = customers[customer.value];
            var value = cents(amount.value);
            var previous = form.dataset.originalCustomer === customer.value &&
                form.dataset.originalMethod === 'fiado' ? cents(form.dataset.originalAmount) || 0 : 0;
            var over = data && value !== null && value > 0 &&
                (!method || method.value === 'fiado') &&
                cents(data.projected) - previous + value > cents(data.limit);
            warning.hidden = !over;
        }

        [customer, amount, method].forEach(function (field) {
            if (!field) return;
            field.addEventListener('input', update);
            field.addEventListener('change', update);
        });
        form.addEventListener('credit-warning-update', update);
        update();
    });

    document.querySelectorAll('.js-edit-payment-btn').forEach(function (button) {
        button.addEventListener('click', function () {
            var form = document.getElementById('edit-payment-form');
            if (!form) return;
            form.dataset.originalCustomer = button.dataset.customerId || '';
            form.dataset.originalMethod = button.dataset.method;
            form.dataset.originalAmount = button.dataset.amount;
            form.dispatchEvent(new Event('credit-warning-update'));
        });
    });
})();
