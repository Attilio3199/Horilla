const CACHE_NAME = 'horilla-v1';
const PRECACHE_URLS = ['/'];

self.addEventListener('install', function (event) {
    event.waitUntil(
        caches.open(CACHE_NAME).then(function (cache) {
            return cache.addAll(PRECACHE_URLS);
        })
    );
    self.skipWaiting();
});

self.addEventListener('activate', function (event) {
    event.waitUntil(
        caches.keys().then(function (cacheNames) {
            return Promise.all(
                cacheNames
                    .filter(function (name) { return name !== CACHE_NAME; })
                    .map(function (name) { return caches.delete(name); })
            );
        })
    );
    self.clients.claim();
});

self.addEventListener('fetch', function (event) {
    // Only handle GET requests for same-origin navigation
    if (event.request.method !== 'GET') return;

    event.respondWith(
        fetch(event.request).catch(function () {
            return caches.match(event.request).then(function (cached) {
                return cached || caches.match('/');
            });
        })
    );
});
