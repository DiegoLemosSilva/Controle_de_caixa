/**
 * Copia o texto do prompt de análise (textarea) para a área de
 * transferência, com um feedback simples no botão.
 *
 * Sem dependências externas, conforme AGENTS.md (JavaScript puro).
 */
(function () {
    var button = document.getElementById('ai-copy-btn');
    var textarea = document.getElementById('ai-prompt-text');

    if (!button || !textarea) {
        return;
    }

    var defaultLabel = button.innerHTML;

    function showFeedback(message) {
        button.textContent = message;
        window.setTimeout(function () {
            button.innerHTML = defaultLabel;
        }, 2000);
    }

    function fallbackCopy() {
        textarea.removeAttribute('readonly');
        textarea.focus();
        textarea.select();
        var copied = false;
        try {
            copied = document.execCommand('copy');
        } catch (err) {
            copied = false;
        }
        textarea.setAttribute('readonly', 'readonly');
        window.getSelection().removeAllRanges();
        return copied;
    }

    button.addEventListener('click', function () {
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(textarea.value).then(
                function () {
                    showFeedback('Copiado!');
                },
                function () {
                    var copied = fallbackCopy();
                    showFeedback(copied ? 'Copiado!' : 'Não foi possível copiar');
                }
            );
        } else {
            var copied = fallbackCopy();
            showFeedback(copied ? 'Copiado!' : 'Não foi possível copiar');
        }
    });
})();
