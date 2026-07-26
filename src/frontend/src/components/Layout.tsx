import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { useAuth } from "../auth/AuthContext";
import { ErrorBoundary } from "./ErrorBoundary";
import { HelpDrawer } from "./HelpDrawer";
import { LanguageToggle } from "./LanguageToggle";
import { VersionBadge } from "./VersionBadge";

type NavLinkSpec = {
  to: string;
  labelKey: string;
  end?: boolean;
  adminOnly?: boolean;
};

// Shared page shell: fluid up to a generous cap so wide monitors are actually
// used, instead of the previous hard 1152px (max-w-6xl) column. Padding scales
// with the breakpoint so narrow screens keep their comfortable gutters.
const SHELL = "mx-auto w-full max-w-[120rem] px-4 sm:px-6 lg:px-8";

const NAV_LINKS: NavLinkSpec[] = [
  { to: "/", labelKey: "nav.dashboard", end: true },
  { to: "/watchlists", labelKey: "nav.watchlists" },
  { to: "/scanner", labelKey: "nav.scanner" },
  { to: "/alerts", labelKey: "nav.alerts" },
  { to: "/news", labelKey: "nav.news" },
  { to: "/discover", labelKey: "nav.discover" },
  { to: "/paper-trading", labelKey: "nav.paperTrading" },
  { to: "/auto-execution", labelKey: "nav.autoExecution" },
  { to: "/docs", labelKey: "nav.docs" },
  { to: "/settings", labelKey: "nav.settings" },
  { to: "/onboarding", labelKey: "nav.setup" },
  { to: "/admin", labelKey: "nav.admin", adminOnly: true },
];

export function Layout() {
  const { t } = useTranslation();
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const visibleLinks = NAV_LINKS.filter(
    (link) => !link.adminOnly || user?.is_admin,
  );

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="border-b border-slate-800 bg-slate-900/70 backdrop-blur">
        <div
          className={`${SHELL} flex min-h-14 flex-wrap items-center justify-between gap-x-4 gap-y-2 py-2`}
        >
          <Link to="/" className="flex items-center gap-2 font-semibold">
            <span className="inline-block h-2 w-2 rounded-full bg-bergt-green" />
            <span>{t("app.title")}</span>
          </Link>
          <nav className="flex min-w-0 flex-wrap items-center gap-1">
            {visibleLinks.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                end={link.end}
                className={({ isActive }) =>
                  `rounded-md px-3 py-1.5 text-sm transition ${
                    isActive
                      ? "bg-slate-800 text-bergt-green"
                      : "text-slate-300 hover:text-bergt-green"
                  }`
                }
              >
                {t(link.labelKey)}
              </NavLink>
            ))}
          </nav>
          <div className="flex shrink-0 items-center gap-3 text-sm text-slate-400">
            <HelpDrawer />
            <LanguageToggle compact />
            {user ? (
              <>
                <span className="hidden max-w-[16rem] truncate xl:inline">
                  {user.email}
                </span>
                <button
                  type="button"
                  onClick={() => {
                    logout();
                    navigate("/login");
                  }}
                  className="btn"
                >
                  {t("nav.logout")}
                </button>
              </>
            ) : null}
          </div>
        </div>
      </header>
      <main className={`${SHELL} py-6`}>
        <ErrorBoundary scope="layout-outlet">
          <Outlet />
        </ErrorBoundary>
      </main>
      <footer className={`${SHELL} pb-4 text-right`}>
        <VersionBadge />
      </footer>
    </div>
  );
}
