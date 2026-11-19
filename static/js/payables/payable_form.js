/**
 * Comportamento do formulário de nova conta a pagar: alterna entre
 * "Única" e os 3 tipos de recorrência (Fixa, Semanal, Parcelada),
 * mostrando apenas os campos relevantes para o modo escolhido.
 *
 * JavaScript puro, sem dependências (AGENTS.md).
 */
(function () {
    var form = document.getElementById('payable-create-form');
    if (!form) {
        return;
    }

    var modeInput = document.getElementById('id_mode');
    var modeButtons = form.querySelectorAll('[data-mode-option]');
    var sections = {
        fixed: document.getElementById('fields-fixed'),
        weekly: document.getElementById('fields-weekly'),
        installment: document.getElementById('fields-installment'),
    };
    var dueDateLabel = document.getElementById('due-date-label');
    var amountLabel = document.getElementById('amount-label');

    var DUE_DATE_LABELS = {
        single: 'Data prevista para pagamento',
        fixed: 'Data da primeira ocorrência',
        weekly: 'Data da primeira ocorrência',
        installment: 'Data da primeira parcela',
    };

    var AMOUNT_LABELS = {
        single: 'Valor',
        fixed: 'Valor de cada ocorrência',
        weekly: 'Valor de cada ocorrência',
        installment: 'Valor de cada parcela',
    };

    function setActiveButton(mode) {
        modeButtons.forEach(function (button) {
            var isActive = button.getAttribute('data-mode-option') === mode;
            button.classList.toggle('payable-mode-btn--active', isActive);
            button.setAttribute('aria-pressed', isActive ? 'true' : 'false');
        });
    }

    function applyMode(mode) {
        modeInput.value = mode;
        setActiveButton(mode);

        Object.keys(sections).forEach(function (key) {
            if (sections[key]) {
                sections[key].hidden = key !== mode;
            }
        });

        if (dueDateLabel && DUE_DATE_LABELS[mode]) {
            dueDateLabel.textContent = DUE_DATE_LABELS[mode];
        }
        if (amountLabel && AMOUNT_LABELS[mode]) {
            amountLabel.textContent = AMOUNT_LABELS[mode];
        }
    }

    modeButtons.forEach(function (button) {
        button.addEventListener('click', function () {
            applyMode(button.getAttribute('data-mode-option'));
        });
    });

    applyMode(modeInput.value || 'single');
})();
