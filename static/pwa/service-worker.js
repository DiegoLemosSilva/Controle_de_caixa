/* O cache contém somente uma página pública; dados financeiros exigem rede. */
const CACHE_NAME = 'controle-caixa-pwa-v2';
const OFFLINE_URL = '/static/pwa/offline.html';

self.addEventListener('install', (event) => {
    event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.add(OFFLINE_URL)));
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((keys) => Promise.all(
            keys.filter((key) => (
                key === 'controle-caixa-static-v1' ||
                (key.startsWith('controle-caixa-pwa-') && key !== CACHE_NAME)
            )).map((key) => caches.delete(key))
        )).then(() => self.clients.claim())
    );
});

self.addEventListener('fetch', (event) => {
    const request = event.request;
    const url = new URL(request.url);

    // Nunca interceptar gravações, respostas privadas não navegáveis ou outras origens.
    if (request.method !== 'GET' || url.origin !== self.location.origin) return;

    if (request.mode === 'navigate') {
        event.respondWith(fetch(request).catch(() => caches.match(OFFLINE_URL)));
    }
});
