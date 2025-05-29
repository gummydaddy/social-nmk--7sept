const CACHE_NAME = "socyfie-v1";

const urlsToCache = [
  // Base pages
  "/",                               // Homepage if applicable
  "/landing_page/",                  // Corrected based on Django path
  "/explore/",                       // Static route
  "/following_media/",              // Corrected path

  // Static files (must match STATIC_URL paths, not local filesystem)
  "/static/css/sb-admin.css",
  "/static/css/sb-admin.min.css",
  "/static/images/android-icon-192x192.png",
  "/static/images/android-icon-512x512.png",
  "/static/images/apple-touch-icon-precomposed.png",
  "/static/images/apple-touch-icon.png",
  "/static/images/favicon.ico",
  "/static/images/favicon.svg",
  "/static/images/logo.png",

  // Manifest and robots.txt
  "/static/manifest.json",
  "/static/robots.txt",
];

// Install event — pre-cache files
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return Promise.all(
        urlsToCache.map((url) => {
          return fetch(url).then((response) => {
            if (!response.ok) {
              console.warn(`Skipped caching ${url}: ${response.statusText}`);
              return;
            }
            return cache.put(url, response);
          }).catch((error) => {
            console.warn(`Failed to cache ${url}:`, error);
          });
        })
      );
    })
  );
});


// Activate event — clean up old caches
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((cache) => {
          if (cache !== CACHE_NAME) {
            return caches.delete(cache);
          }
        })
      );
    })
  );
});

// Fetch event — serve from cache or fallback to network
self.addEventListener("fetch", (event) => {
  event.respondWith(
    caches.match(event.request).then((response) => {
      return (
        response ||
        fetch(event.request).catch(() => {
          // Optional fallback (add offline.html if needed)
          return caches.match("/offline/");
        })
      );
    })
  );
});
