/* service-worker.js  (v3)
 *
 * Pages, scripts and data are fetched NETWORK-FIRST so volunteers always get the
 * newest nav.html / form page. The saved copy is only a fallback for bad signal or
 * offline. Only the icons are cache-first.
 */
const CACHE_NAME = 'lv-nav-pwa-v3';          // bumped: deletes the old v2 cache on activate
const NETWORK_TIMEOUT_MS = 6000;             // after this, fall back to the saved copy

// Saved on install so the app can still open with no signal.
const PRECACHE = [
  '/',
  '/nav.html',
  '/manifest.json',
  '/icons/icon-192.png',
  '/icons/icon-512.png'
];

self.addEventListener('install', event => {
  self.skipWaiting();   // take over right away instead of waiting for all tabs to close
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache =>
      Promise.all(
        PRECACHE.map(url =>
          // cache:'reload' skips the browser's own HTTP cache, so we never save a stale copy
          cache.add(new Request(url, { cache: 'reload' }))
            .catch(err => console.warn('SW precache skipped', url, err))
        )
      )
    )
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

function withTimeout(promise, ms) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('timeout')), ms);
    promise.then(
      value => { clearTimeout(timer); resolve(value); },
      error => { clearTimeout(timer); reject(error); }
    );
  });
}

// Try the network first. Keep the newest good copy for offline use.
// If the network is slow or down, use the saved copy.
async function networkFirst(request, cacheKey, fetchOptions) {
  const cache = await caches.open(CACHE_NAME);

  const networkPromise = fetch(request, fetchOptions).then(response => {
    if (response && response.ok) {
      cache.put(cacheKey, response.clone()).catch(e => console.warn('SW cache put failed', e));
    }
    return response;
  });
  networkPromise.catch(() => {});   // avoid "unhandled rejection" noise if the timeout wins

  try {
    return await withTimeout(networkPromise, NETWORK_TIMEOUT_MS);
  } catch (err) {
    const cached = await cache.match(cacheKey);
    if (cached) return cached;
    return networkPromise;          // nothing saved: keep waiting for the network
  }
}

async function cacheFirst(request) {
  const cache = await caches.open(CACHE_NAME);
  const cached = await cache.match(request);
  if (cached) return cached;
  const response = await fetch(request);
  if (response && response.ok) {
    cache.put(request, response.clone()).catch(() => {});
  }
  return response;
}

self.addEventListener('fetch', event => {
  const request = event.request;
  if (request.method !== 'GET') return;     // let the browser handle POST/PUT/etc.

  const url = new URL(request.url);

  // Route API + Mapbox: network-first, last good response as fallback (same as before)
  const isApi = url.hostname.includes('execute-api') || url.hostname.includes('mapbox.com');
  if (isApi) {
    event.respondWith(networkFirst(request, request, undefined));
    return;
  }

  if (url.origin !== self.location.origin) return;   // ignore any other site

  // Icons almost never change: cache-first is fine
  if (url.pathname.startsWith('/icons/')) {
    event.respondWith(cacheFirst(request));
    return;
  }

  // Everything else on our site (pages, scripts, manifest, photos): network-first.
  // cache:'no-cache' makes the browser re-check with the server every time.
  // The saved copy is keyed by path only, so '/?event=Formula1' and '/' share one
  // always-current entry, and nav.html?zone=A... all share one.
  const cacheKey = new Request(url.origin + url.pathname);
  event.respondWith(networkFirst(request, cacheKey, { cache: 'no-cache' }));
});
