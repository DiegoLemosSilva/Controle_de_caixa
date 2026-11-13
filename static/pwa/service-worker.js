/**
 * Service Worker do Controle de Caixa.
 *
 * Por decisão de projeto (AGENTS.md seção 15), este Service Worker NÃO
 * armazena em cache páginas autenticadas nem respostas financeiras.
 * Apenas arquivos estáticos públicos (CSS, JS, ícones) são cacheados,
 * para permitir instalação como PWA sem risco de expor dados privados
 * após logout ou expiração de sessão.
 */

const CACHE_NAME = 'controle-caixa-static-v1';

const STATIC_ASSETS = [
    '/static/css/app.css',
];

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))
    );
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((keys) =>
            Promise.all(
                keys
                    .filter((key) => key !== CACHE_NAME)
                    .map((key) => caches.delete(key))
            )
        )
    );
});

self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);

    // Só intercepta requisições de arquivos estáticos públicos.
    const isStaticAsset = url.pathname.startsWith('/static/');

    if (!isStaticAsset || event.request.method !== 'GET') {
        return;
    }

    event.respondWith(
        caches.match(event.request).then((cached) => {
            return cached || fetch(event.request);
        })
    );
});
