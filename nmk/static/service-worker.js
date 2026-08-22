const CACHE_NAME = 'socyfie-v3.1.4';

// Minimal pre-cache list — only truly static assets that never redirect
const PRE_CACHE_URLS = [
  '/static/images/android-icon-192x192.png',
  '/static/images/android-icon-512x512.png',
  '/static/images/logo.png',
  "/static/images/apple-touch-icon-precomposed.png",
  "/static/images/apple-touch-icon.png",
  "/static/images/favicon.ico",
  "/static/images/favicon.svg",
  "/templates/user_profile/following_media.html",
  "/templates/user_profile/media_detail.html",
  "/templates/user_profile/profile.html",
  "/templates/landings/landing_page.html",
  "/static/js/install-pwa.js",
  "/static/js/pull_to_refresh.js",
  "/feed/",
  "/explore_me/",
  "/upload_media/",
  "/notion_home/",
  "/landing_page/",
];


// ─────────────────────────────────────────────────────────────────────────────
// Install – pre-cache a small set of static assets
// ─────────────────────────────────────────────────────────────────────────────
self.addEventListener('install', function (event) {
  // skipWaiting so the new SW takes over immediately (replaces broken v1/v2)
  self.skipWaiting();

  event.waitUntil(
    caches.open(CACHE_NAME).then(function (cache) {
      // allSettled – a single failed asset doesn't abort the install
      return Promise.allSettled(
        PRE_CACHE_URLS.map(function (url) { return cache.add(url); })
      );
    })
  );
});


// ─────────────────────────────────────────────────────────────────────────────
// Activate – delete every old cache so stale SWs don't interfere
// ─────────────────────────────────────────────────────────────────────────────
self.addEventListener('activate', function (event) {
  event.waitUntil(
    caches.keys()
      .then(function (cacheNames) {
        return Promise.all(
          cacheNames
            .filter(function (name) { return name !== CACHE_NAME; })
            .map(function (name) { return caches.delete(name); })
        );
      })
      .then(function () {
        // Take control of all open pages immediately
        return self.clients.claim();
      })
  );
});


// ─────────────────────────────────────────────────────────────────────────────
// Fetch – cache-first for /static/ assets ONLY
//
// ⚠️  SAFARI RULE: Never call event.respondWith() for navigation requests.
//     If we intercept a navigation and the server returns a redirect,
//     Safari throws "Response served by service worker has redirections"
//     and the page fails to load. Return early → browser handles natively.
// ─────────────────────────────────────────────────────────────────────────────
self.addEventListener('fetch', function (event) {
  var req = event.request;
  var url;

  try { url = new URL(req.url); } catch (_) { return; }

  // ── Hard pass-throughs (never intercept these) ───────────────────────────

  // 1. PAGE NAVIGATIONS — THE SAFARI FIX
  //    Covers: GET /feed/, GET /login/, GET /message/..., any Django redirect
  if (req.mode === 'navigate') { return; }

  // 2. Non-GET methods (POST, PUT, DELETE …)
  if (req.method !== 'GET') { return; }

  // 3. Cross-origin requests (CDN fonts, analytics, etc.)
  if (url.origin !== self.location.origin) { return; }

  // 4. WebSocket upgrade requests
  if (req.url.indexOf('/ws/') !== -1) { return; }

  // 5. Django API / view endpoints  (anything NOT under /static/)
  //    These may redirect, require auth, or return varying content
  if (url.pathname.indexOf('/static/') !== 0) { return; }

  // 6. HTML files (shouldn't exist under /static/ but guard anyway)
  if (url.pathname.slice(-5) === '.html' ||
      url.pathname.slice(-4) === '.htm') { return; }

  // ── Cache-first for verified /static/ assets ─────────────────────────────
  event.respondWith(
    caches.match(req).then(function (cached) {
      if (cached) { return cached; }

      return fetch(req).then(function (networkResponse) {
        // Only cache clean, non-redirect, same-origin responses
        if (
          networkResponse &&
          networkResponse.status === 200 &&
          networkResponse.type === 'basic'   // same-origin only
        ) {
          var toCache = networkResponse.clone();
          caches.open(CACHE_NAME).then(function (cache) {
            cache.put(req, toCache);
          });
        }
        return networkResponse;
      }).catch(function () {
        // Network failed and nothing in cache → return nothing
        // (browser shows its own offline error; safer than serving wrong page)
      });
    })
  );
});


// ─────────────────────────────────────────────────────────────────────────────
// Push – show notification
// ─────────────────────────────────────────────────────────────────────────────
self.addEventListener('push', function (event) {
  var payload = {};
  try {
    payload = event.data ? event.data.json() : {};
  } catch (_) {
    payload = {
      title: 'Socyfie',
      body : event.data ? event.data.text() : 'New notification',
    };
  }

  var title = payload.title || 'Socyfie';
  var options = {
    body              : payload.body   || '',
    icon              : payload.icon   || '/static/images/android-icon-192x192.png',
    badge             : payload.badge  || '/static/images/android-icon-192x192.png',
    tag               : payload.tag    || 'socyfie',
    renotify          : true,
    requireInteraction: payload.requireInteraction === true,
    data              : payload,
    vibrate           : [200, 100, 200],
  };

  if (payload.type === 'incoming_call') {
    options.requireInteraction = true;
    options.renotify = true;
    if (payload.caller_pic) { options.image = payload.caller_pic; }
    if (payload.actions) { options.actions = payload.actions; }
  }

  event.waitUntil(
    self.registration.showNotification(title, options)
  );
});


// ─────────────────────────────────────────────────────────────────────────────
// Notification click – open or focus the target page
// ─────────────────────────────────────────────────────────────────────────────
self.addEventListener('notificationclick', function (event) {
  var data = event.notification.data || {};
  event.notification.close();

  // ── Decline: reject the call from the background, no page needed ──────
  if (event.action === 'decline-call' && data.call_id) {
    event.waitUntil(
      fetch('/message/api/call/' + data.call_id + '/decline/', {
        method: 'POST',
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
      }).catch(function () {})
    );
    return;
  }

  // ── Accept (or a plain tap): open the call page ────────────────────────
  var targetUrl = data.url || '/';

  if (event.action === 'accept-call' && data.call_id) {
    targetUrl = '/call/' + data.call_id + '/?action=accept';
  } else if (data.type === 'incoming_call' && data.call_id) {
    targetUrl = '/call/' + data.call_id + '/';
  }

  // Make absolute
  if (targetUrl.charAt(0) === '/') {
    targetUrl = self.location.origin + targetUrl;
  }

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true })
      .then(function (windowClients) {
        // Focus an already-open tab at exactly that URL
        for (var i = 0; i < windowClients.length; i++) {
          if (windowClients[i].url === targetUrl && 'focus' in windowClients[i]) {
            return windowClients[i].focus();
          }
        }
        // Navigate any open tab to the target URL
        for (var j = 0; j < windowClients.length; j++) {
          if ('navigate' in windowClients[j]) {
            return windowClients[j].navigate(targetUrl)
              .then(function (c) { return c && c.focus(); });
          }
        }
        // No open tab — open a new window
        if (clients.openWindow) {
          return clients.openWindow(targetUrl);
        }
      })
  );
});
