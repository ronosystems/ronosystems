const CACHE_NAME = 'pos-cache-v1';
const ASSETS = [
    '/epa_shop/pos/',
    '/static/vendor/bootstrap/bootstrap.min.css',
    '/static/vendor/fontawesome/css/all.min.css',
];

self.addEventListener('install', (e) => {
    self.skipWaiting();
    e.waitUntil(
        caches.open(CACHE_NAME).then((cache) => cache.addAll(ASSETS))
    );
});

self.addEventListener('fetch', (e) => {
    if (e.request.method !== 'GET') return;
    e.respondWith(
        caches.match(e.request).then((response) => {
            return response || fetch(e.request);
        })
    );
});
