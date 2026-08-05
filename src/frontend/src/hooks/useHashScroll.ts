/**
 * Springt zu dem Element, dessen id im URL-Fragment steht.
 *
 * Der Router rendert Routen clientseitig; der Browser hat das Fragment beim
 * Navigieren laengst verarbeitet, bevor das Zielelement ueberhaupt im DOM ist.
 * Ohne diesen Hook landen Kontext-Spruenge wie "/settings#mfa" (aus dem
 * Onboarding) oder "/watchlists#<id>" (aus der Provider-Coverage-Kachel)
 * kommentarlos oben auf einer langen Seite — der Nutzer sucht dann selbst.
 *
 * Ein rAF genuegt nicht immer, weil die Zielsektion oft erst nach dem ersten
 * Datenpaket rendert. Deshalb wird bis zu einer Sekunde lang in kurzen
 * Abstaenden nachgesehen und beim ersten Treffer gescrollt.
 */
import { useEffect } from "react";
import { useLocation } from "react-router-dom";

const RETRY_INTERVAL_MS = 100;
const MAX_WAIT_MS = 1000;

export function useHashScroll(): void {
  const { hash } = useLocation();

  useEffect(() => {
    if (!hash || hash.length < 2) return;

    let elapsed = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const targetId = decodeURIComponent(hash.slice(1));

    const attempt = () => {
      // getElementById statt querySelector: Watchlist-Ids sind UUIDs und
      // beginnen teilweise mit einer Ziffer, was als CSS-Selektor ungueltig
      // waere und querySelector werfen liesse.
      const el = document.getElementById(targetId);
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "start" });
        return;
      }
      elapsed += RETRY_INTERVAL_MS;
      if (elapsed < MAX_WAIT_MS) {
        timer = setTimeout(attempt, RETRY_INTERVAL_MS);
      }
    };

    timer = setTimeout(attempt, 0);
    return () => {
      if (timer) clearTimeout(timer);
    };
  }, [hash]);
}
