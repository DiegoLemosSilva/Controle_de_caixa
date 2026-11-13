/**
 * Autocomplete de produtos em JavaScript puro, sem dependências.
 *
 * Criado para substituir o <datalist> nativo do HTML5, que tem
 * comportamento inconsistente entre navegadores (especialmente em
 * dispositivos móveis) e não permite controlar a aparência da lista
 * de sugestões. Funciona bem com centenas de produtos, pois filtra
 * tudo em memória no navegador (sem requisições ao servidor a cada
 * tecla digitada).
 *
 * Uso:
 *   initProductSearch({
 *     inputId: 'id-do-campo-de-busca',
 *     products: [{id, name, price}, ...],
 *     onSelect: function (product) { ... }
 *   });
 */
(function (window) {
    'use strict';

    function normalize(text) {
        return (text || '')
            .toLowerCase()
            .normalize('NFD')
            .replace(/[\u0300-\u036f]/g, '');
    }

    function formatPrice(price) {
        return 'R$ ' + Number(price).toFixed(2).replace('.', ',');
    }

    function initProductSearch(options) {
        var input = document.getElementById(options.inputId);
        if (!input) {
            return;
        }

        var products = options.products || [];
        var onSelect = options.onSelect || function () {};
        var maxResults = options.maxResults || 8;

        var wrapper = document.createElement('div');
        wrapper.className = 'position-relative';
        input.parentNode.insertBefore(wrapper, input);
        wrapper.appendChild(input);

        var resultsBox = document.createElement('div');
        resultsBox.className = 'list-group position-absolute w-100 shadow-sm product-search-results';
        resultsBox.style.display = 'none';
        resultsBox.style.zIndex = '1060';
        resultsBox.style.maxHeight = '260px';
        resultsBox.style.overflowY = 'auto';
        wrapper.appendChild(resultsBox);

        var activeIndex = -1;
        var currentMatches = [];

        function renderResults(matches) {
            currentMatches = matches;
            activeIndex = -1;
            resultsBox.innerHTML = '';

            if (matches.length === 0) {
                resultsBox.style.display = 'none';
                return;
            }

            matches.forEach(function (product, index) {
                var item = document.createElement('button');
                item.type = 'button';
                item.className = 'list-group-item list-group-item-action d-flex justify-content-between align-items-center';
                item.dataset.index = index;

                var nameSpan = document.createElement('span');
                nameSpan.className = 'text-truncate';
                nameSpan.textContent = product.name;

                var priceSpan = document.createElement('span');
                priceSpan.className = 'text-muted small ms-3 flex-shrink-0';
                priceSpan.textContent = formatPrice(product.price);

                item.appendChild(nameSpan);
                item.appendChild(priceSpan);

                item.addEventListener('mousedown', function (event) {
                    event.preventDefault();
                    selectProduct(product);
                });

                resultsBox.appendChild(item);
            });

            resultsBox.style.display = 'block';
        }

        function updateActiveHighlight() {
            var items = resultsBox.querySelectorAll('.list-group-item');
            items.forEach(function (item, index) {
                item.classList.toggle('active', index === activeIndex);
            });
            if (activeIndex >= 0 && items[activeIndex]) {
                items[activeIndex].scrollIntoView({ block: 'nearest' });
            }
        }

        function selectProduct(product) {
            input.value = product.name;
            resultsBox.style.display = 'none';
            onSelect(product);
        }

        function search(term) {
            var normalizedTerm = normalize(term);
            if (!normalizedTerm) {
                renderResults([]);
                return;
            }
            var matches = products.filter(function (product) {
                return normalize(product.name).indexOf(normalizedTerm) !== -1;
            }).slice(0, maxResults);
            renderResults(matches);
        }

        input.addEventListener('input', function () {
            search(input.value);
        });

        input.addEventListener('keydown', function (event) {
            if (resultsBox.style.display === 'none') {
                return;
            }
            if (event.key === 'ArrowDown') {
                event.preventDefault();
                activeIndex = Math.min(activeIndex + 1, currentMatches.length - 1);
                updateActiveHighlight();
            } else if (event.key === 'ArrowUp') {
                event.preventDefault();
                activeIndex = Math.max(activeIndex - 1, 0);
                updateActiveHighlight();
            } else if (event.key === 'Enter') {
                if (activeIndex >= 0 && currentMatches[activeIndex]) {
                    event.preventDefault();
                    selectProduct(currentMatches[activeIndex]);
                }
            } else if (event.key === 'Escape') {
                resultsBox.style.display = 'none';
            }
        });

        input.addEventListener('blur', function () {
            // Pequeno atraso para permitir o mousedown no item ser processado
            // antes de esconder a lista (blur dispara antes do click).
            window.setTimeout(function () {
                resultsBox.style.display = 'none';
            }, 100);
        });

        input.addEventListener('focus', function () {
            if (input.value) {
                search(input.value);
            }
        });
    }

    window.initProductSearch = initProductSearch;
})(window);
