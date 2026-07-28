/**
 * Mark a guided-run step as visited once the page has really rendered.
 *
 * Called from the pages themselves rather than from the wizard's links, so the
 * step reflects that the user actually arrived and saw content -- clicking a
 * link that then fails to load does not count.
 *
 * No-op while the tour has not been started (see `markTourVisit`), so normal
 * use of the app never pre-fills a tour the user has not begun.
 */
import { useEffect } from "react";

import { useAuth } from "../auth/AuthContext";
import { markTourVisit, type TourVisit } from "./tourState";

export function useTourVisit(visit: TourVisit, when = true): void {
  const { user } = useAuth();
  useEffect(() => {
    if (!user || !when) return;
    markTourVisit(user.id, visit);
  }, [user, visit, when]);
}
