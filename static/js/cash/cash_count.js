(function () {
    var dateInput = document.getElementById('cash-count-date');
    if (dateInput && dateInput.form) {
        dateInput.addEventListener('change', function () {
            dateInput.form.requestSubmit();
        });
    }
})();
