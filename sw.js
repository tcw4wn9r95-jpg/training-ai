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
