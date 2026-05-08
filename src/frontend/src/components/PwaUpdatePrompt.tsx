import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

// Lazy-load the registerSW helper. The virtual module is provided by
// vite-plugin-pwa at build time; the dynamic import keeps it out of
// the initial bundle on browsers that aren't going to register a
// service worker anyway (no-SW environments still load the rest of
// the app fine).

export function PwaUpdatePrompt() {
  const { t } = useTranslation();
  const [needsRefresh, setNeedsRefresh] = useState(false);
  const [offlineReady, setOfflineReady] = useState(false);
  const [updateFn, setUpdateFn] = useState<(() => Promise<void>) | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!("serviceWorker" in navigator)) return;
    let cancelled = false;
    (async () => {
      try {
        const mod = await import(/* @vite-ignore */ "virtual:pwa-register");
        const update = mod.registerSW({
          onNeedRefresh() {
            if (!cancelled) setNeedsRefresh(true);
          },
          onOfflineReady() {
            if (!cancelled) setOfflineReady(true);
          },
          onRegisterError(err: unknown) {
            console.warn("Service worker registration failed", err);
          },
        });
        if (!cancelled) {
          setUpdateFn(() => () => update(true));
        }
      } catch (err) {
        // No service worker support, or build did not produce one — no-op.
        console.debug("PWA registration skipped", err);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (!needsRefresh && !offlineReady) return null;

  return (
    <div
      className="fixed bottom-4 right-4 z-50 max-w-sm rounded-lg border border-slate-700 bg-slate-900 p-3 text-sm text-slate-200 shadow-2xl"
      role="status"
      data-testid="pwa-update-prompt"
    >
      {needsRefresh ? (
        <div className="space-y-2">
          <p>{t("pwa.updateAvailable")}</p>
          <div className="flex gap-2">
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => updateFn?.()}
            >
              {t("pwa.reload")}
            </button>
            <button
              type="button"
              className="btn"
              onClick={() => setNeedsRefresh(false)}
            >
              {t("pwa.later")}
            </button>
          </div>
        </div>
      ) : (
        <div className="flex items-center justify-between gap-2">
          <span>{t("pwa.offlineReady")}</span>
          <button
            type="button"
            className="btn"
            onClick={() => setOfflineReady(false)}
          >
            {t("pwa.ok")}
          </button>
        </div>
      )}
    </div>
  );
}
