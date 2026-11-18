(function () {
    var form = document.querySelector('[data-cash-count-batch]');
    if (!form) return;

    function cents(value) {
        var match = String(value).trim().replace(',', '.').match(/^(\d+)(?:\.(\d{1,2}))?$/);
        if (!match) return null;
        var whole = Number(match[1]);
        if (!Number.isSafeInteger(whole) || whole > 9999999999) return null;
        return whole * 100 + Number((match[2] || '').padEnd(2, '0'));
    }

    var closeButton = document.querySelector('[data-close-cash]');
    form.addEventListener('input', function () {
        if (closeButton) closeButton.disabled = true;
    });

    form.querySelectorAll('input[name^="counted_"]').forEach(function (input) {
        var method = input.name.slice('counted_'.length);
        var expected = form.elements.namedItem('expected_' + method);
        var output = input.closest('.card-body').querySelector('[data-count-difference]');
        if (!expected || !output) return;

        function update() {
            var actual = cents(input.value);
            var base = cents(expected.value);
            if (actual === null || base === null) {
                output.textContent = '';
                return;
            }
            var difference = actual - base;
            if (difference === 0) {
                output.textContent = 'Sem diferença';
                return;
            }
            var amount = (Math.abs(difference) / 100).toLocaleString('pt-BR', {
                minimumFractionDigits: 2, maximumFractionDigits: 2
            });
            output.textContent = (difference > 0 ? 'Sobra' : 'Falta') + ' prevista: R$ ' + amount;
        }

        input.addEventListener('input', update);
        update();
    });
})();
