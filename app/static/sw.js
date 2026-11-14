/*
  sw.js - Plern service worker

  Strategy
    - HTML pages          : always network (data comes from SQL Server)
    - /static/js, /static/css : network first, cache as a fallback
      (so a deploy is picked up immediately, never a stale player)
    - other /static/*     : cache first, then network
    - /static/audio/*     : never cached (175 MB, previews are streamed)

  Bump CACHE_VERSION when you want to drop the old cache entirely.
*/
const CACHE_VERSION = 'plern-v2';
const SHELL = [
  '/static/css/style.css',
  '/static/css/mobile.css',
  '/static/css/fonts.css',
  '/static/js/player.js',
  '/static/js/ambient.js',
  '/static/img/logo.svg',
  '/static/img/favicon.svg'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_VERSION)
      .then((cache) => cache.addAll(SHELL))
      .catch(() => undefined)
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE_VERSION).map((key) => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

function putInCache(request, response) {
  if (!response || response.status !== 200) return response;
  const copy = response.clone();
  caches.open(CACHE_VERSION).then((cache) => cache.put(request, copy));
  return response;
}

self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (!url.pathname.startsWith('/static/')) return;      // pages: network only
  if (url.pathname.startsWith('/static/audio/')) return; // audio: never cache

  // code assets must always be fresh
  const isCode = url.pathname.startsWith('/static/js/') || url.pathname.startsWith('/static/css/');
  if (isCode) {
    event.respondWith(
      fetch(request)
        .then((response) => putInCache(request, response))
        .catch(() => caches.match(request))
    );
    return;
  }

  event.respondWith(
    caches.match(request).then((hit) => hit || fetch(request).then((response) => putInCache(request, response)))
  );
});
