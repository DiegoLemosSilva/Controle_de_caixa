(function () {
    var script = document.currentScript;
    if ('serviceWorker' in navigator && script && script.dataset.serviceWorkerUrl) {
        navigator.serviceWorker.register(script.dataset.serviceWorkerUrl);
    }
})();
