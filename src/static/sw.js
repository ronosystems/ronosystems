const CACHE_NAME = 'Version 5';

// ============================================================
// Core pages — pre-cached during install
// Everything else caches lazily on first visit
// ============================================================
const ASSETS = [
    // ============ PUBLIC ============
    '/',
    '/about/',
    '/contact/',
    '/features/',
    '/pricing/',
    '/help/',
    '/support/',
    '/terms/',
    '/privacy/',

    // ============ DASHBOARD / HOME ============
    '/dashboard/',
    '/epa_shop/dashboard/',

    // ============ POS (critical) ============
    '/epa_shop/pos/',

    // ============ SALES ============
    '/epa_shop/sales/',
    '/epa_shop/sales/single/',

    // ============ PRODUCTS & INVENTORY ============
    '/epa_shop/products/',
    '/epa_shop/products/add/',
    '/epa_shop/inventory/',
    '/epa_shop/inventory/low-stock/',
    '/epa_shop/inventory/movement/',
    '/epa_shop/inventory/stock-restock/',
    '/epa_shop/categories/',
    '/epa_shop/units/',
    '/epa_shop/units/phones/',
    '/epa_shop/units/electronics/',

    // ============ STORE MGMT ============
    '/company/branches/',
    '/company/employees/',
    '/company/settings/',
    '/company/expenses/',
    '/company/reports/',

    // ============ FINANCE ============
    '/epa_shop/finance/',

    // ============ STATIC (offline CSS/JS/icons) ============
    '/static/vendor/bootstrap/bootstrap.min.css',
    '/static/vendor/bootstrap/bootstrap.bundle.min.js',
    '/static/vendor/fontawesome/css/all.min.css',
    '/static/vendor/chartjs/chart.umd.min.js',
    '/static/images/icon-192.png',
    '/static/images/icon-512.png',
];

// ============================================================
// INSTALL — pre-cache core assets (tolerates individual failures)
// ============================================================
self.addEventListener('install', (e) => {
    self.skipWaiting();
    e.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            return Promise.all(
                ASSETS.map((url) =>
                    cache.add(url).catch((err) => {
                        console.warn('[SW] Failed to cache:', url, err);
                    })
                )
            );
        })
    );
});

// ============================================================
// ACTIVATE — remove old caches
// ============================================================
self.addEventListener('activate', (e) => {
    e.waitUntil(
        caches.keys().then((keys) =>
            Promise.all(
                keys
                    .filter((key) => key !== CACHE_NAME)
                    .map((key) => caches.delete(key))
            )
        ).then(() => self.clients.claim())
    );
});

// ============================================================
// FETCH — network-first, cache fallback
// ============================================================
self.addEventListener('fetch', (e) => {
    if (e.request.method !== 'GET') return;

    const url = e.request.url;

    // Never cache dynamic / auth-sensitive URLs
    if (url.includes('/api/') ||
        url.includes('/pos/search/') ||
        url.includes('/pos/pending/') ||
        url.includes('/sale/') ||
        url.includes('/mpesa/') ||
        url.includes('/accounts/') ||
        url.includes('/auth/') ||
        url.includes('/manifest.json') ||
        url.includes('/sw.js') ||
        url.includes('/.well-known/') ||
        url.includes('/admin/')) {
        return;
    }

    e.respondWith(
        fetch(e.request)
            .then((response) => {
                // Cache successful responses for offline
                const responseClone = response.clone();
                caches.open(CACHE_NAME).then((cache) => {
                    cache.put(e.request, responseClone);
                });
                return response;
            })
            .catch(() => caches.match(e.request))
    );
});

// ============================================================
// MESSAGE — allow page to skip waiting
// ============================================================
self.addEventListener('message', (event) => {
    if (event.data === 'SKIP_WAITING') {
        self.skipWaiting();
    }
});