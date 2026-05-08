<!-- page: /docs/mobile -->
# Mobile / Android (PWA)

NexusPulse Trade ships as an installable Progressive Web App. Open the app in Chrome on Android, tap the browser menu, and choose **Install app** (or **Add to home screen**). The app then opens in standalone mode without the browser chrome — same experience as a native installation.

## What "installed" gives you

- **Home-screen icon** with the brand colour, no URL bar.
- **Offline fallback**: if you're on a flaky connection, the last cached state of the dashboard, watchlists, scanner, and analysis pages still renders. API requests will then fail individually (showing "—" for missing values) instead of breaking the whole UI.
- **Push notifications** continue to work the same way they did in the browser — the VAPID web-push setup is shared.

## How updates work

When a new version is deployed, the next time you open the app a small "A new version is ready" prompt slides in from the bottom-right corner. Tap **Reload** to apply the update or **Later** to keep the current version. Updates are downloaded silently in the background.

## Caching strategy

- **API calls** under `/api/*` use a network-first strategy with a 5-second timeout — so you always see fresh data when online and the last cached payload when offline.
- **Static assets** (JS, CSS, fonts, SVGs) use cache-first with a 7-day expiration. That's why the app loads instantly after the first visit.
- **Navigation** falls back to the cached `index.html` when offline so the SPA shell keeps rendering.

## iOS / Safari

iOS-Safari supports PWA installation but doesn't yet support all the manifest fields. The home-screen icon works, the service worker works, but background sync and push notifications are limited. Fully native iOS / Android wrappers are planned for a later wave (Capacitor + biometric auth) — the PWA is the fast path that gets you 80% of the value today.

## Where the rules live

- Manifest + service-worker config: `src/frontend/vite.config.ts` (`VitePWA` plugin block)
- Update prompt component: `src/frontend/src/components/PwaUpdatePrompt.tsx`
- Icon source: `src/frontend/public/icon.svg`
