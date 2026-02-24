/* service-worker.js */
const CACHE_NAME = 'lv-nav-pwa-v3';

// Only precache *same-origin* app shell assets.
// Keep this list small and stable.
const STATIC_ASSETS = [
  '/nav.html',
  '/manifest.json',
  '/service-worker.js',
  '/icons/icon-192.png',
  '/icons/icon-512.png'
];

self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(CACHE_NAME);

    // Add assets one-by-one so a single failure doesn't break install.
    await Promise.allSettled(
      STATIC_ASSETS.map(async (url) => {
        try {
          await cache.add(url);
        } catch (e) {
          // Don’t fail install if one asset can’t be cached
          console.warn('SW precache failed:', url, e);
        }
      })
    );

    self.skipWaiting();
  })());
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)));
    await self.clients.claim();
  })());
});

self.addEventListener('fetch', (event) => {
  const req = event.request;

  // Only handle GET requests
  if (req.method !== 'GET') return;

  const url = new URL(req.url);
  const sameOrigin = url.origin === self.location.origin;

  const isAwsApi = url.hostname.includes('execute-api');
  const isMapbox = url.hostname.includes('mapbox.com');

  // Don’t SW-cache Mapbox resources (avoid huge caches / opaque responses / token issues).
  if (isMapbox) {
    event.respondWith(fetch(req));
    return;
  }

  // Network-first for AWS API (destinations), fallback to cache if offline
  if (isAwsApi) {
    event.respondWith((async () => {
      try {
        const fresh = await fetch(req);
        // Cache successful API responses
        const cache = await caches.open(CACHE_NAME);
        cache.put(req, fresh.clone()).catch(() => {});
        return fresh;
      } catch (e) {
        const cached = await caches.match(req);
        if (cached) return cached;
        throw e;
      }
    })());
    return;
  }

  // Cache-first for same-origin static assets (HTML/CSS/JS/icons)
  if (sameOrigin) {
    event.respondWith((async () => {
      const cached = await caches.match(req);
      if (cached) return cached;

      const fresh = await fetch(req);
      const cache = await caches.open(CACHE_NAME);
      cache.put(req, fresh.clone()).catch(() => {});
      return fresh;
    })());
    return;
  }

  // For all other cross-origin (not Mapbox), just passthrough
  event.respondWith(fetch(req));
});
