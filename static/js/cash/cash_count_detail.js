(function () {
    var expectedAmount = parseFloat(
        document.getElementById('expected-amount').dataset.value.replace(',', '.')
    );
    var countedInput = document.getElementById('id_counted_amount');
    var reasonField = document.getElementById('reason-field');
    var divergenceAlert = document.getElementById('divergence-alert');
    var submitBtn = document.getElementById('submit-btn');

    function formatMoney(value) {
        return value.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    function updateUI() {
        var counted = parseFloat(countedInput.value);
        if (isNaN(counted)) {
            reasonField.hidden = true;
            divergenceAlert.classList.add('d-none');
            submitBtn.textContent = 'Confirmar (sem divergência)';
            return;
        }

        var difference = Math.round((counted - expectedAmount) * 100) / 100;

        if (difference === 0) {
            reasonField.hidden = true;
            divergenceAlert.classList.add('d-none');
            submitBtn.textContent = 'Confirmar (sem divergência)';
            submitBtn.classList.remove('btn-warning');
            submitBtn.classList.add('btn-primary');
        } else {
            reasonField.hidden = false;
            divergenceAlert.classList.remove('d-none');
            if (difference > 0) {
                divergenceAlert.textContent = 'Sobra de R$ ' + formatMoney(difference) + '. Informe a justificativa abaixo.';
            } else {
                divergenceAlert.textContent = 'Falta de R$ ' + formatMoney(Math.abs(difference)) + '. Informe a justificativa abaixo.';
            }
            submitBtn.textContent = 'Registrar divergência';
            submitBtn.classList.remove('btn-primary');
            submitBtn.classList.add('btn-warning');
        }
    }

    countedInput.addEventListener('input', updateUI);
    updateUI();
})();
