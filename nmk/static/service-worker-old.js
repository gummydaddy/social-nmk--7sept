const CACHE_NAME = "socyfie-v2.5";   // ← bumped from v1.1

const urlsToCache = [
  "/",
  //"/landing_page/",
  //"/explore/",
  //"/following_media/",
  "/static/css/sb-admin.css",
  "/static/css/sb-admin.min.css",
  "/static/images/android-icon-192x192.png",
  "/static/images/android-icon-512x512.png",
  "/static/images/apple-touch-icon-precomposed.png",
  "/static/images/apple-touch-icon.png",
  "/static/images/favicon.ico",
  "/static/images/favicon.svg",
  "/static/images/logo.png",
  "/static/manifest.json",
  //"/static/robots.txt",
];


// ─────────────────────────────────────────────────────────────────────────────
// Install – pre-cache static assets
// ─────────────────────────────────────────────────────────────────────────────
self.addEventListener("install", (event) => {
  self.skipWaiting();   // activate immediately
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) =>
      Promise.all(
        urlsToCache.map((url) =>
          fetch(url)
            //.then((res) => { if (res.ok) cache.put(url, res); })
              .then((res) => {
                  if (res.ok && !res.redirected) {
                    return cache.put(url, res.clone());
                  }
              })
              .catch(() => { /* skip if offline during install */ })
        )
      )
    )
  );
});

// ─────────────────────────────────────────────────────────────────────────────
// Activate – clean up old caches
// ─────────────────────────────────────────────────────────────────────────────
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((names) =>
        Promise.all(
          names
            .filter((n) => n !== CACHE_NAME)
            .map((n) => caches.delete(n))
        )
      )
      .then(() => self.clients.claim())   // take control immediately
  );
});

// ─────────────────────────────────────────────────────────────────────────────
// Fetch – serve from cache, fall back to network
// ─────────────────────────────────────────────────────────────────────────────

// Let POST requests (share target, AJAX) go straight to the network
//self.addEventListener("fetch", (event) => {
  //if (event.request.method !== "GET") return;

  // WebSocket upgrades are handled by the browser natively
  //if (event.request.url.includes("/ws/")) return;

  //event.respondWith(
    //caches.match(event.request).then(
      //(cached) => cached || fetch(event.request).catch(() => caches.match("/"))
    //)
  //);
//});


self.addEventListener("fetch", (event) => {
    // Let normal page navigations go directly to the network
    if (event.request.mode === "navigate") {
        return;
    }

    // Never intercept API requests
    if (event.request.url.includes("/api/")) {
      return;
    }

    if (event.request.url.includes("/ws/")) {
        return;
    }

    if (event.request.method !== "GET") {
        return;
    }

  event.respondWith(
    caches.match(event.request).then(
      (cached) => cached || fetch(event.request).catch(() => caches.match("/"))

    //event.respondWith(
        //caches.match(event.request).then((cached) => {
            //return cached || fetch(event.request);
        //})
    );
});


// Navigation: return app shell for deep links so the SPA can handle routing
//self.addEventListener("fetch", (event) => {
  //if (event.request.mode !== "navigate") return;
  //const url = new URL(event.request.url);
  //if (url.pathname.startsWith("/media/")
     //url.pathname.startsWith("/explore_detail/")) {
    //event.respondWith(
      //caches.match("/landing.html").then(response => {
        //return response || fetch("/landing.html")
    //);
  //}
//});

// ─────────────────────────────────────────────────────────────────────────────
// [NEW] Web Push – receive push event from server
// ─────────────────────────────────────────────────────────────────────────────
self.addEventListener("push", (event) => {
  let payload = {};
  try {
    payload = event.data ? event.data.json() : {};
  } catch (_) {
    payload = { title: "Socyfie", body: event.data ? event.data.text() : "" };
  }

  const title   = payload.title  || "Socyfie";
  const body    = payload.body   || "";
  const icon    = payload.icon   || "/static/images/android-icon-192x192.png";
  const badge   = payload.badge  || "/static/images/android-icon-192x192.png";
  const tag     = payload.tag    || "socyfie-notification";
  const requireInteraction = payload.requireInteraction || false;

  // Build notification options
  const options = {
    body,
    icon,
    badge,
    tag,
    renotify   : true,       // ring again even if same tag already showing
    requireInteraction,
    data       : payload,    // pass full payload so notificationclick can use it
    vibrate    : [200, 100, 200],
  };

  // ── Call-specific options ──────────────────────────────────────────────────
  if (payload.type === "incoming_call") {
    options.requireInteraction = true;
    // Action buttons (best-effort; not all browsers support them)
    options.actions = [
      { action: "open_app", title: "Open App ↗" },
    ];
    // Show caller avatar as image (supported in Chrome/Android)
    if (payload.caller_pic) {
      options.image = payload.caller_pic;
    }
  }

  // ── Message-specific options ───────────────────────────────────────────────
  if (payload.type === "new_message" && payload.sender) {
    options.actions = [
      { action: "reply", title: "Open Chat ↗" },
    ];
  }

  event.waitUntil(
    self.registration.showNotification(title, options)
  );
});

// ─────────────────────────────────────────────────────────────────────────────
// [NEW] Notification click – focus existing tab or open new one
// ─────────────────────────────────────────────────────────────────────────────
self.addEventListener("notificationclick", (event) => {
  event.notification.close();

  const data   = event.notification.data || {};
  const action = event.action;          // "" = body click, "reply" / "open_app" = button

  // Determine destination URL
  let targetUrl = "/";
  if (data.url) {
    targetUrl = data.url;
  } else if (data.type === "new_message" && data.sender) {
    targetUrl = `/user_messages_view/${data.sender}/`;
  } else if (data.type === "incoming_call" && data.caller) {
    targetUrl = data.url || `/`;
  }

  // Ensure the URL is absolute
  const base = self.location.origin;
  if (targetUrl.startsWith("/")) {
    targetUrl = base + targetUrl;
  }

  event.waitUntil(
    clients
      .matchAll({ type: "window", includeUncontrolled: true })
      .then((windowClients) => {
        // Try to reuse an already-open window at the same origin
        for (const client of windowClients) {
          // Focus any open window and navigate it to the target
          if ("navigate" in client && "focus" in client) {
            return client.navigate(targetUrl).then((c) => c && c.focus());
          }
        }
        // No open window – open a new one
        if (clients.openWindow) {
          return clients.openWindow(targetUrl);
        }
      })
  );
});

// ─────────────────────────────────────────────────────────────────────────────
// [NEW] Notification dismiss (optional – analytics / cleanup)
// ─────────────────────────────────────────────────────────────────────────────
self.addEventListener("notificationclose", (_event) => {
  // Could POST a "dismissed" event to the server here for analytics
});

