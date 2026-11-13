(function () {
    var productsDataEl = document.getElementById('sale-products-data');
    if (productsDataEl && window.initProductSearch) {
        var products = JSON.parse(productsDataEl.textContent);
        window.initProductSearch({
            inputId: 'sale-product-search',
            products: products,
            onSelect: function (product) {
                var descriptionField = document.getElementById('id_description');
                if (descriptionField) descriptionField.value = product.name;
            },
        });
    }
})();
