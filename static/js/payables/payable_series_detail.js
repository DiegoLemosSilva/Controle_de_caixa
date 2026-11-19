/**
 * Confirmação simples antes de enviar formulários marcados com
 * data-confirm, usada nas ações destrutivas da tela de série
 * (cancelar ocorrências futuras). JavaScript puro, sem dependências.
 */
(function () {
    document.querySelectorAll('form[data-confirm]').forEach(function (form) {
        form.addEventListener('submit', function (event) {
            var message = form.getAttribute('data-confirm');
            if (message && !window.confirm(message)) {
                event.preventDefault();
            }
        });
    });
})();
