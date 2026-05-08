import { Suspense, lazy, useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";

import { apiFetch } from "../api/client";

// Lazy-load the markdown renderer so react-markdown + remark-gfm only
// land in the bundle once the user opens the drawer.
const HelpMarkdown = lazy(() => import("./HelpMarkdown"));

type DocTopic = {
  slug: string;
  title: string;
  page?: string | null;
  content?: string;
};

type DocsTopicsResponse = {
  topics: DocTopic[];
  pageMap: Record<string, string>;
};

function resolveSlug(pathname: string, pageMap: Record<string, string>): string | null {
  // Exact match first, then progressively shorter prefixes so /analysis/AAPL
  // still resolves to the /analysis topic.
  if (pageMap[pathname]) return pageMap[pathname];
  const segments = pathname.split("/").filter(Boolean);
  while (segments.length > 0) {
    const candidate = "/" + segments.join("/");
    if (pageMap[candidate]) return pageMap[candidate];
    segments.pop();
  }
  if (pageMap["/"]) return pageMap["/"];
  return null;
}

export function HelpDrawer() {
  const [open, setOpen] = useState(false);
  const [pageMap, setPageMap] = useState<Record<string, string> | null>(null);
  const [topic, setTopic] = useState<DocTopic | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const location = useLocation();

  useEffect(() => {
    if (pageMap !== null) return;
    apiFetch<DocsTopicsResponse>("/api/docs/topics", { skipAuth: true })
      .then((payload) => setPageMap(payload.pageMap || {}))
      .catch(() => setPageMap({}));
  }, [pageMap]);

  useEffect(() => {
    if (!open || !pageMap) return;
    const slug = resolveSlug(location.pathname, pageMap);
    if (!slug) {
      setTopic(null);
      setError("No help available for this page yet.");
      return;
    }
    setLoading(true);
    setError(null);
    apiFetch<DocTopic>(`/api/docs/${slug}`, { skipAuth: true })
      .then((payload) => setTopic(payload))
      .catch(() => setError("Could not load help."))
      .finally(() => setLoading(false));
  }, [open, location.pathname, pageMap]);

  return (
    <>
      <button
        type="button"
        className="btn"
        aria-label="Open contextual help"
        data-testid="help-drawer-toggle"
        onClick={() => setOpen(true)}
      >
        ?
      </button>
      {open ? (
        <div
          className="fixed inset-0 z-40"
          aria-modal="true"
          role="dialog"
          aria-label="Help"
        >
          <button
            type="button"
            aria-label="Close help drawer"
            className="absolute inset-0 bg-slate-950/60 backdrop-blur-sm"
            onClick={() => setOpen(false)}
          />
          <aside
            className="absolute inset-y-0 right-0 w-full max-w-md overflow-y-auto border-l border-slate-800 bg-slate-900 p-6 shadow-2xl"
            data-testid="help-drawer-panel"
          >
            <header className="flex items-center justify-between">
              <h2 className="text-base font-semibold text-slate-100">
                {topic?.title ?? "Help"}
              </h2>
              <button
                type="button"
                className="btn"
                onClick={() => setOpen(false)}
                aria-label="Close help"
              >
                Close
              </button>
            </header>
            <div className="mt-4 space-y-3 text-sm text-slate-200">
              {loading ? <p className="text-slate-400">Loading…</p> : null}
              {error ? <p className="text-amber-300">{error}</p> : null}
              {topic?.content ? (
                <Suspense fallback={<p className="text-slate-400">Loading…</p>}>
                  <HelpMarkdown content={topic.content} />
                </Suspense>
              ) : null}
              <div className="border-t border-slate-800 pt-3 text-xs text-slate-400">
                <Link
                  to={topic?.slug ? `/docs/${topic.slug}` : "/docs"}
                  className="hover:text-bergt-green"
                  onClick={() => setOpen(false)}
                >
                  Open the full documentation →
                </Link>
              </div>
            </div>
          </aside>
        </div>
      ) : null}
    </>
  );
}
