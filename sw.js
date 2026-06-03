var SW_VERSION = '20260602-4';

// On install, skip waiting so new SW activates immediately
self.addEventListener('install', function(event) {
  self.skipWaiting();
});

// On activate, claim all clients so this SW controls every open tab right away
self.addEventListener('activate', function(event) {
  event.waitUntil(self.clients.claim());
});

// Network-first for HTML navigation: always try the network so updates land
// immediately. Falls back to cache only if completely offline.
self.addEventListener('fetch', function(event) {
  var req = event.request;
  if (req.mode === 'navigate' || req.url.indexOf('dashboard.html') > -1) {
    event.respondWith(
      fetch(req).catch(function() { return caches.match(req); })
    );
    return;
  }
  // All other requests pass through normally
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
