(function () {
    var modalEl = document.getElementById('editDayModal');
    var modal = new bootstrap.Modal(modalEl);

    document.querySelectorAll('.js-edit-day-card').forEach(function (card) {
        card.addEventListener('click', function () {
            document.getElementById('edit-day-indicator').value = card.dataset.indicator;
            document.getElementById('edit-day-date').value = card.dataset.date;
            document.getElementById('edit-day-amount').value = card.dataset.planned;
            document.getElementById('edit-day-title').textContent =
                'Editar previsão - ' + card.dataset.label + ' (' + card.dataset.dateDisplay + ')';
            modal.show();
        });
    });
})();
