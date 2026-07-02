var SW_VERSION = '20260702-1';
var SHELL_CACHE = 'shell-' + SW_VERSION;
var CDN_CACHE = 'cdn-v1';
var SHELL = ['./', './dashboard.html', './manifest.json', './apple-touch-icon.png', './icon-192.png', './icon-512.png'];

// On install, precache the app shell and skip waiting so the new SW activates immediately
self.addEventListener('install', function(event) {
  event.waitUntil(
    caches.open(SHELL_CACHE)
      .then(function(c) { return c.addAll(SHELL); })
      .catch(function() {})
      .then(function() { return self.skipWaiting(); })
  );
});

// On activate, drop old shell caches and claim all clients
self.addEventListener('activate', function(event) {
  event.waitUntil(
    caches.keys().then(function(keys) {
      return Promise.all(keys.map(function(k) {
        if (k.indexOf('shell-') === 0 && k !== SHELL_CACHE) return caches.delete(k);
      }));
    }).then(function() { return self.clients.claim(); })
  );
});

// HTML navigation: network-first so updates land immediately, cached shell as
// the offline fallback. CDN assets (Chart.js, fonts): stale-while-revalidate
// so the home-screen app opens instantly and works offline.
self.addEventListener('fetch', function(event) {
  var req = event.request;
  if (req.method !== 'GET') return;
  if (req.mode === 'navigate' || req.url.indexOf('dashboard.html') > -1) {
    event.respondWith(
      fetch(req).then(function(res) {
        var copy = res.clone();
        caches.open(SHELL_CACHE).then(function(c) { c.put(req, copy); });
        return res;
      }).catch(function() {
        return caches.match(req).then(function(m) { return m || caches.match('./dashboard.html'); });
      })
    );
    return;
  }
  if (req.url.indexOf('cdnjs.cloudflare.com') > -1 || req.url.indexOf('fonts.googleapis.com') > -1 || req.url.indexOf('fonts.gstatic.com') > -1) {
    event.respondWith(
      caches.match(req).then(function(cached) {
        var net = fetch(req).then(function(res) {
          if (res && (res.ok || res.type === 'opaque')) {
            var copy = res.clone();
            caches.open(CDN_CACHE).then(function(c) { c.put(req, copy); });
          }
          return res;
        }).catch(function() { return cached; });
        return cached || net;
      })
    );
    return;
  }
  // All other requests (GitHub data) pass through normally
});

self.addEventListener('push', function(event) {
  if (!event.data) return;
  var d;
  try { d = event.data.json(); } catch(e) { d = { body: event.data.text() }; }
  event.waitUntil(
    self.registration.showNotification(d.title || 'Coach Claudio', {
      body: d.body || "Check tomorrow's training plan",
      icon: 'apple-touch-icon.png',
      badge: 'apple-touch-icon.png',
      tag: 'daily-plan',
      renotify: true,
      data: { url: './dashboard.html' }
    })
  );
});

self.addEventListener('notificationclick', function(event) {
  event.notification.close();
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function(cs) {
      for (var i = 0; i < cs.length; i++) {
        if (cs[i].url.indexOf('dashboard') > -1 && 'focus' in cs[i]) return cs[i].focus();
      }
      return clients.openWindow('./dashboard.html');
    })
  );
});
