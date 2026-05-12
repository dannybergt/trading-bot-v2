<!-- page: /docs/mobile -->
# Mobile / Android (PWA)

NexusPulse Trade wird als installierbare Progressive Web App ausgeliefert. Oeffne die App im Chrome auf Android, tippe auf das Browser-Menue und waehle **App installieren** (oder **Zum Startbildschirm hinzufuegen**). Die App startet dann im Standalone-Modus ohne Browser-Chrome — gleiches Gefuehl wie eine native Installation.

## Was "installiert" dir bringt

- **Home-Screen-Icon** mit der Brand-Farbe, ohne URL-Leiste.
- **Offline-Fallback**: bei wackliger Verbindung rendert der zuletzt gecachte Stand von Dashboard, Watchlists, Scanner und Analyse weiter. API-Requests scheitern dann einzeln (mit "—" fuer fehlende Werte), statt das ganze UI zu brechen.
- **Push-Benachrichtigungen** funktionieren weiter wie im Browser — das VAPID-Web-Push-Setup wird geteilt.

## Wie Updates ablaufen

Beim Deployment einer neuen Version erscheint beim naechsten App-Start unten rechts ein kleiner Hinweis "A new version is ready". Tippe **Reload** zum Anwenden oder **Later** um die aktuelle Version zu behalten. Updates laden im Hintergrund leise nach.

## Caching-Strategie

- **API-Calls** unter `/api/*` nutzen Network-First mit 5 Sekunden Timeout — du siehst frische Daten online und den letzten gecachten Payload offline.
- **Statische Assets** (JS, CSS, Fonts, SVGs) nutzen Cache-First mit 7-Tage-Ablauf. Deshalb laedt die App nach dem ersten Besuch sofort.
- **Navigation** faellt auf das gecachte `index.html` zurueck, wenn offline, so dass die SPA-Hose weiter rendert.

## iOS / Safari

iOS-Safari unterstuetzt PWA-Installation, aber noch nicht alle Manifest-Felder. Home-Screen-Icon funktioniert, Service Worker funktioniert, aber Background-Sync und Push-Notifications sind eingeschraenkt. Voll-native iOS-/Android-Wrapper sind fuer eine spaetere Welle geplant (Capacitor + Biometric Auth) — die PWA ist der schnelle Pfad, der heute 80 Prozent des Nutzens liefert.

## Wo die Regeln liegen

- Manifest + Service-Worker-Config: `src/frontend/vite.config.ts` (`VitePWA`-Plugin-Block)
- Update-Prompt-Komponente: `src/frontend/src/components/PwaUpdatePrompt.tsx`
- Icon-Quelle: `src/frontend/public/icon.svg`
