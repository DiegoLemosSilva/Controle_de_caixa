(function () {
    document.querySelectorAll('.js-confirm-product-delete').forEach(function (form) {
        form.addEventListener('submit', function (event) {
            if (!window.confirm('Excluir este produto? Esta ação não pode ser desfeita.')) {
                event.preventDefault();
            }
        });
    });
})();
