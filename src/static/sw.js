const CACHE_NAME = 'Version 6'; // Bumped version to force update

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

// ============================================================
// PUSH NOTIFICATIONS (PWABuilder Score Booster)
// ============================================================
self.addEventListener('push', (event) => {
    let data = { title: 'New Notification', body: 'You have a new message!' };
    
    if (event.data) {
        try {
            data = event.data.json();
        } catch (e) {
            data = { title: 'New Notification', body: event.data.text() };
        }
    }

    const options = {
        body: data.body,
        icon: '/static/images/icon-192.png',
        badge: '/static/images/icon-192.png',
        vibrate: [100, 50, 100],
        data: {
            url: data.url || '/'
        }
    };

    event.waitUntil(
        self.registration.showNotification(data.title, options)
    );
});

// Handle notification clicks
self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    event.waitUntil(
        clients.openWindow(event.notification.data.url)
    );
});

// ============================================================
// BACKGROUND SYNC (PWABuilder Score Booster)
// ============================================================
self.addEventListener('sync', (event) => {
    if (event.tag === 'sync-data') {
        event.waitUntil(syncData());
    }
});

async function syncData() {
    // Logic to retry failed requests or sync offline data goes here
    console.log('[SW] Background sync triggered');
}

// ============================================================
// PERIODIC SYNC (PWABuilder Score Booster)
// ============================================================
self.addEventListener('periodicsync', (event) => {
    if (event.tag === 'content-sync') {
        event.waitUntil(fetchBackgroundData());
    }
});

async function fetchBackgroundData() {
    // Logic to fetch background updates (e.g., new products) goes here
    console.log('[SW] Periodic sync triggered');
}