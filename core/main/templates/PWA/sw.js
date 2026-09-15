// This tells the browser to cache your app files for speed
const CACHE_NAME = 'mbpi-v1';

self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('fetch', (event) => {
  // This allows the app to fetch resources from the network
  event.respondWith(fetch(event.request).catch(() => caches.match(event.request)));
});