import { useEffect, useState } from "react";
import { Link, NavLink, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { apiFetch } from "../api/client";
import HelpMarkdown from "../components/HelpMarkdown";

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

const ROOT_SLUG = "getting-started";

export function DocsPage() {
  const { t } = useTranslation();
  const { slug } = useParams();
  const targetSlug = slug || ROOT_SLUG;
  const [topics, setTopics] = useState<DocTopic[]>([]);
  const [topic, setTopic] = useState<DocTopic | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    apiFetch<DocsTopicsResponse>("/api/docs/topics", { skipAuth: true })
      .then((payload) => setTopics(payload.topics || []))
      .catch(() => setTopics([]));
  }, []);

  useEffect(() => {
    setLoading(true);
    setError(null);
    apiFetch<DocTopic>(`/api/docs/${targetSlug}`, { skipAuth: true })
      .then((payload) => setTopic(payload))
      .catch(() => {
        setTopic(null);
        setError(t("docs.missing"));
      })
      .finally(() => setLoading(false));
  }, [targetSlug, t]);

  return (
    <div className="grid gap-6 lg:grid-cols-[220px_1fr]" data-testid="docs-page">
      <nav className="card space-y-2 self-start">
        <h2 className="text-xs uppercase tracking-wide text-slate-400">
          {t("docs.sidebarTitle")}
        </h2>
        <ul className="space-y-1 text-sm">
          {topics.length === 0 ? (
            <li className="text-slate-500">{t("docs.loading")}</li>
          ) : null}
          {topics.map((entry) => (
            <li key={entry.slug}>
              <NavLink
                to={`/docs/${entry.slug}`}
                className={({ isActive }) =>
                  `block rounded px-2 py-1 ${
                    isActive
                      ? "bg-slate-800 text-bergt-green"
                      : "text-slate-300 hover:text-bergt-green"
                  }`
                }
              >
                {entry.title}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
      <article className="card">
        {loading ? <p className="text-sm text-slate-400">{t("docs.loading")}</p> : null}
        {error ? (
          <div className="space-y-2 text-sm text-amber-300">
            <p>{error}</p>
            <Link to="/docs" className="text-bergt-green hover:underline">
              {t("docs.back")}
            </Link>
          </div>
        ) : null}
        {topic && !error ? <HelpMarkdown content={topic.content || ""} /> : null}
      </article>
    </div>
  );
}
