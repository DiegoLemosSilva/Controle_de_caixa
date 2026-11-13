(function () {
    var addItemProductsDataEl = document.getElementById('add-item-products-data');
    if (addItemProductsDataEl && window.initProductSearch) {
        var products = JSON.parse(addItemProductsDataEl.textContent);
        window.initProductSearch({
            inputId: 'add-item-product-search',
            products: products,
            onSelect: function (product) {
                var descriptionField = document.getElementById('id_description');
                var priceField = document.getElementById('id_unit_price');
                if (descriptionField) descriptionField.value = product.name;
                if (priceField) priceField.value = product.price;
            },
        });
    }

    document.querySelectorAll('.js-edit-item-btn').forEach(function (button) {
        button.addEventListener('click', function () {
            document.getElementById('edit-item-id').value = button.dataset.itemId;
            document.getElementById('edit-item-description').value = button.dataset.description;
            document.getElementById('edit-item-quantity').value = button.dataset.quantity;
            document.getElementById('edit-item-unit-price').value = button.dataset.unitPrice;
        });
    });

    var methodField = document.getElementById('id_method');
    var customerField = document.getElementById('payment-customer-field');
    if (methodField && customerField) {
        function toggleCustomerField() {
            customerField.hidden = methodField.value !== 'fiado';
        }
        methodField.addEventListener('change', toggleCustomerField);
        toggleCustomerField();
    }

    var editMethodField = document.getElementById('edit-payment-method');
    var editCustomerField = document.getElementById('edit-payment-customer-field');
    function toggleEditCustomerField() {
        if (editMethodField && editCustomerField) {
            editCustomerField.hidden = editMethodField.value !== 'fiado';
        }
    }
    if (editMethodField) {
        editMethodField.addEventListener('change', toggleEditCustomerField);
    }

    document.querySelectorAll('.js-edit-payment-btn').forEach(function (button) {
        button.addEventListener('click', function () {
            document.getElementById('edit-payment-id').value = button.dataset.paymentId;
            document.getElementById('edit-payment-method').value = button.dataset.method;
            document.getElementById('edit-payment-amount').value = button.dataset.amount;
            document.getElementById('edit-payment-customer').value = button.dataset.customerId || '';
            toggleEditCustomerField();
        });
    });

    document.querySelectorAll('form[data-confirm]').forEach(function (form) {
        form.addEventListener('submit', function (event) {
            if (!window.confirm(form.dataset.confirm)) {
                event.preventDefault();
            }
        });
    });
})();
