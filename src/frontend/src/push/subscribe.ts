/**
 * Web-Push-Abonnement im Browser.
 *
 * Die Serverseite ist seit Phase 4 vollstaendig (VAPID-Pruefung, Dispatcher,
 * Hintergrundtask, Versand bei Scanner-Signal, Paper-Fill und ab 2026-08-05
 * auch bei Alarmregeln). Der Empfaenger fehlte: im gesamten Frontend gab es
 * keinen `pushManager`-Aufruf, jede gesendete Benachrichtigung lief ins Leere.
 *
 * Bewusst kein Automatismus beim Seitenaufruf: ein ungefragter
 * Berechtigungsdialog ist die zuverlaessigste Art, dauerhaft blockiert zu
 * werden. Der Nutzer loest das Abonnement in den Einstellungen aus.
 */
import { apiFetch } from "../api/client";

export type PushSupportState =
  | "unsupported"
  | "unconfigured"
  | "denied"
  | "default"
  | "subscribed";

type PushConfig = { configured: boolean; publicKey: string | null };

/**
 * VAPID-Schluessel kommen base64url-kodiert; pushManager will rohe Bytes.
 *
 * Der Rueckgabetyp ist bewusst `Uint8Array<ArrayBuffer>` und nicht nur
 * `Uint8Array`: seit TypeScript die Sicht auf den zugrundeliegenden Puffer
 * generisch macht, umfasst der Standardtyp auch `SharedArrayBuffer` — und der
 * ist kein `BufferSource`, was `applicationServerKey` verlangt. Deshalb wird
 * der Puffer hier explizit angelegt.
 */
function urlBase64ToUint8Array(base64String: string): Uint8Array<ArrayBuffer> {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = window.atob(base64);
  const buffer = new ArrayBuffer(raw.length);
  const output = new Uint8Array(buffer);
  for (let i = 0; i < raw.length; i += 1) output[i] = raw.charCodeAt(i);
  return output;
}

function arrayBufferToBase64(buffer: ArrayBuffer | null): string {
  if (!buffer) return "";
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let i = 0; i < bytes.byteLength; i += 1) binary += String.fromCharCode(bytes[i]);
  return window.btoa(binary);
}

export function isPushSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    "serviceWorker" in navigator &&
    "PushManager" in window &&
    "Notification" in window
  );
}

/** Zustand ohne jede Nebenwirkung — insbesondere ohne Berechtigungsdialog. */
export async function readPushState(): Promise<PushSupportState> {
  if (!isPushSupported()) return "unsupported";

  let config: PushConfig;
  try {
    config = await apiFetch<PushConfig>("/api/auth/push/config");
  } catch {
    return "unconfigured";
  }
  if (!config.configured || !config.publicKey) return "unconfigured";

  if (Notification.permission === "denied") return "denied";

  const registration = await navigator.serviceWorker.getRegistration();
  const existing = await registration?.pushManager.getSubscription();
  if (existing) return "subscribed";

  return Notification.permission === "granted" ? "default" : "default";
}

/**
 * Fordert die Berechtigung an, abonniert und meldet das Abonnement am Server.
 * Wirft mit einer sprechenden Ursache, damit die Oberflaeche nicht "irgendwas
 * ging schief" anzeigen muss.
 */
export async function subscribeToPush(): Promise<PushSupportState> {
  if (!isPushSupported()) throw new Error("push_unsupported");

  const config = await apiFetch<PushConfig>("/api/auth/push/config");
  if (!config.configured || !config.publicKey) throw new Error("push_unconfigured");

  const permission = await Notification.requestPermission();
  if (permission !== "granted") throw new Error("push_permission_denied");

  // Der Service Worker wird von PwaUpdatePrompt registriert; hier wird nur
  // darauf gewartet, statt eine zweite Registrierung anzulegen.
  const registration = await navigator.serviceWorker.ready;

  const existing = await registration.pushManager.getSubscription();
  const subscription =
    existing ??
    (await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(config.publicKey),
    }));

  await apiFetch("/api/auth/push/subscribe", {
    method: "POST",
    body: {
      endpoint: subscription.endpoint,
      p256dh: arrayBufferToBase64(subscription.getKey("p256dh")),
      auth: arrayBufferToBase64(subscription.getKey("auth")),
    },
  });

  return "subscribed";
}
