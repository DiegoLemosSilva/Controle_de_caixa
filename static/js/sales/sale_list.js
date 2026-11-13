(function () {
    var toggleButton = document.getElementById('toggle-values-btn');

    if (toggleButton) {
        var hiddenLabel = toggleButton.dataset.hiddenLabel;
        var visibleLabel = toggleButton.dataset.visibleLabel;
        var isHidden = true;

        function applyState() {
            var values = document.querySelectorAll('.js-money-value');
            values.forEach(function (element) {
                element.textContent = isHidden ? 'R$ ••••••' : 'R$ ' + element.dataset.value;
            });
            toggleButton.textContent = isHidden ? hiddenLabel : visibleLabel;
            toggleButton.setAttribute('aria-pressed', String(!isHidden));
        }

        toggleButton.addEventListener('click', function () {
            isHidden = !isHidden;
            applyState();
        });

        // Por padrão, os valores ficam ocultos até o usuário clicar em "Mostrar valores".
        applyState();
    }

    document.querySelectorAll('.js-confirm-sale-cancel').forEach(function (form) {
        form.addEventListener('submit', function (event) {
            if (!window.confirm('Cancelar esta venda?')) {
                event.preventDefault();
            }
        });
    });
})();
