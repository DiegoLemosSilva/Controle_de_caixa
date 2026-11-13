(function () {
    var button = document.getElementById('toggle-values-btn');
    var visible = false;
    button.addEventListener('click', function () {
        visible = !visible;
        document.querySelectorAll('.js-money-value').forEach(function (element) {
            element.textContent = visible ? 'R$ ' + element.dataset.value : 'R$ ••••••';
        });
        button.textContent = visible ? '🙈 Ocultar valores' : '👁️ Mostrar valores';
        button.setAttribute('aria-pressed', String(visible));
    });
})();
