/* service-worker.js */
const CACHE_NAME = 'lv-nav-pwa-v2';

// Cache-first for static shell, network-first for APIs
const STATIC_ASSETS = [
  '/nav.html',
  '/manifest.json',
  '/service-worker.js',
  '/icons/icon-192.png',
  '/icons/icon-512.png'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(STATIC_ASSETS))
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys
          .filter(k => k !== CACHE_NAME)
          .map(k => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', event => {
  const request = event.request;
  const requestUrl = new URL(request.url);

  // Only handle GET requests for caching
  if (request.method !== 'GET') {
    return; // let the browser handle POST/PUT/etc.
  }

  const isApi =
    requestUrl.hostname.includes('execute-api') ||
    requestUrl.hostname.includes('mapbox.com');

  // Network-first for API & Mapbox
  if (isApi) {
    event.respondWith(
      fetch(request)
        .then(response => {
          // cache a copy of successful GET responses
          const responseClone = response.clone();
          caches.open(CACHE_NAME).then(cache => {
            try {
              cache.put(request, responseClone);
            } catch (e) {
              // ignore caching errors for safety
              console.warn('SW cache put (api) failed', e);
            }
          });
          return response;
        })
        .catch(() => caches.match(request))
    );
    return;
  }

  // Cache-first for static assets & navigation
  event.respondWith(
    caches.match(request).then(cached => {
      if (cached) return cached;

      return fetch(request).then(response => {
        const responseClone = response.clone();
        caches.open(CACHE_NAME).then(cache => {
          try {
            cache.put(request, responseClone);
          } catch (e) {
            console.warn('SW cache put (static) failed', e);
          }
        });
        return response;
      });
    })
  );
});
