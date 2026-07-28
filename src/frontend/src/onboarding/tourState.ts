/**
 * Local state for the guided first run.
 *
 * The tour reports progress from REAL artifacts: a watchlist entry, an alert
 * rule and a paper order the user actually created. Counting those outright
 * would lie, because a fresh account is seeded with starter watchlists that
 * already contain seven symbols -- "you added a symbol" would be green before
 * the user did anything.
 *
 * So the tour records a baseline when it starts and only counts what appears
 * ON TOP of it. That is honest for brand new accounts and for existing users
 * who run the tour later, and it needs no knowledge of what the seed contains.
 *
 * Two steps have no artifact to count (finding a symbol, reading an analysis).
 * Those are marked when the corresponding page actually rendered -- not when
 * the user clicked a link -- so they cannot be completed by intent alone.
 *
 * Kept out of React so it stays a pure, testable module and so pages can mark
 * a visit without subscribing to tour state.
 */

export type TourCounts = {
  watchlistItems: number;
  alertRules: number;
  paperOrders: number;
};

export type TourVisit = "scanner" | "analysis";

export type TourRecord = {
  version: 1;
  /** Counts at the moment the tour started; null until then. */
  baseline: TourCounts | null;
  visited: Partial<Record<TourVisit, boolean>>;
  startedAt: string | null;
  completedAt: string | null;
};

const VERSION = 1;

export const EMPTY_TOUR: TourRecord = {
  version: VERSION,
  baseline: null,
  visited: {},
  startedAt: null,
  completedAt: null,
};

/** Per user, so a shared browser does not leak one account's progress into another. */
export function tourStorageKey(userId: number | string): string {
  return `tradingBot.guidedTour.v${VERSION}.${userId}`;
}

function storage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    // Private mode / disabled storage: the tour degrades to "not started"
    // rather than breaking the page.
    return null;
  }
}

export function readTour(userId: number | string): TourRecord {
  const store = storage();
  if (!store) return EMPTY_TOUR;
  try {
    const raw = store.getItem(tourStorageKey(userId));
    if (!raw) return EMPTY_TOUR;
    const parsed = JSON.parse(raw) as Partial<TourRecord>;
    if (parsed?.version !== VERSION) return EMPTY_TOUR;
    return {
      version: VERSION,
      baseline: parsed.baseline ?? null,
      visited: parsed.visited ?? {},
      startedAt: parsed.startedAt ?? null,
      completedAt: parsed.completedAt ?? null,
    };
  } catch {
    return EMPTY_TOUR;
  }
}

export function writeTour(userId: number | string, record: TourRecord): void {
  const store = storage();
  if (!store) return;
  try {
    store.setItem(tourStorageKey(userId), JSON.stringify(record));
  } catch {
    // Quota or disabled storage -- progress is cosmetic, never block the UI.
  }
}

export function startTour(
  userId: number | string,
  counts: TourCounts,
  now: string,
): TourRecord {
  const record: TourRecord = {
    version: VERSION,
    baseline: counts,
    visited: {},
    startedAt: now,
    completedAt: null,
  };
  writeTour(userId, record);
  return record;
}

export function resetTour(userId: number | string): void {
  const store = storage();
  if (!store) return;
  try {
    store.removeItem(tourStorageKey(userId));
  } catch {
    // ignore
  }
}

/**
 * Record that a page of the tour actually rendered.
 *
 * No-op when the tour was never started, so browsing the app normally does not
 * silently pre-complete a tour the user has not begun.
 */
export function markTourVisit(userId: number | string, visit: TourVisit): void {
  const record = readTour(userId);
  if (!record.startedAt || record.visited[visit]) return;
  writeTour(userId, { ...record, visited: { ...record.visited, [visit]: true } });
}

export function completeTour(userId: number | string, now: string): TourRecord {
  const record = readTour(userId);
  const next = { ...record, completedAt: now };
  writeTour(userId, next);
  return next;
}

/** True once `current` exceeds what was already there when the tour started. */
export function grewSinceBaseline(
  baseline: TourCounts | null,
  current: number,
  field: keyof TourCounts,
): boolean {
  if (!baseline) return false;
  return current > baseline[field];
}
