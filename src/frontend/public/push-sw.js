/**
 * Web-Push-Handler fuer den Service Worker.
 *
 * Wird ueber `workbox.importScripts` in den von vite-plugin-pwa erzeugten
 * Service Worker eingehaengt (siehe vite.config.ts). Bewusst als separate
 * Datei statt als Umstellung auf `injectManifest`: der Push-Teil ist klein und
 * unabhaengig von der Caching-Strategie, und ein Wechsel der Build-Strategie
 * haette das gesamte Offline-Verhalten mit angefasst.
 *
 * Hintergrund: die Serverseite war seit Phase 4 vollstaendig — VAPID-Pruefung,
 * Dispatcher, Hintergrundtask, Push beim Scanner-Signal und beim Paper-Fill.
 * Nur den Empfaenger gab es nicht: im gesamten Frontend fand sich kein
 * `pushManager`. Jede gesendete Benachrichtigung lief damit ins Leere.
 */

self.addEventListener("push", (event) => {
  let payload = {};
  if (event.data) {
    try {
      payload = event.data.json();
    } catch {
      // Aeltere oder fremde Sender schicken reinen Text.
      payload = { body: event.data.text() };
    }
  }

  const title = payload.title || "NexusPulse";
  const options = {
    body: payload.body || "",
    icon: "/icon.svg",
    badge: "/icon.svg",
    // Der Zielpfad wird beim Klick gebraucht; er darf kein Fremd-Origin sein
    // (siehe notificationclick unten).
    data: { url: typeof payload.url === "string" ? payload.url : "/" },
    // Gleichartige Meldungen ersetzen einander, statt sich zu stapeln.
    tag: payload.tag || title,
    renotify: false,
  };

  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();

  const raw = (event.notification.data && event.notification.data.url) || "/";
  // Nur eigene Pfade oeffnen. Eine Nutzlast kommt zwar vom eigenen Server,
  // trägt aber Symbolnamen aus Nutzereingaben und Provider-Antworten — ein
  // absoluter Fremd-Link darf daraus nie werden.
  const target = new URL(raw, self.location.origin);
  const path =
    target.origin === self.location.origin ? target.pathname + target.search : "/";

  event.waitUntil(
    self.clients
      .matchAll({ type: "window", includeUncontrolled: true })
      .then((clientList) => {
        for (const client of clientList) {
          if (client.url.startsWith(self.location.origin) && "focus" in client) {
            client.navigate(path);
            return client.focus();
          }
        }
        return self.clients.openWindow(path);
      }),
  );
});
