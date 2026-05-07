import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";

const NAV_LINKS = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/watchlists", label: "Watchlists" },
  { to: "/scanner", label: "Scanner" },
  { to: "/alerts", label: "Alerts" },
  { to: "/settings", label: "Settings" },
];

export function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="border-b border-slate-800 bg-slate-900/70 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-4">
          <Link to="/" className="flex items-center gap-2 font-semibold">
            <span className="inline-block h-2 w-2 rounded-full bg-bergt-green" />
            <span>NexusPulse Trade</span>
          </Link>
          <nav className="flex items-center gap-1">
            {NAV_LINKS.map((link) => (
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
                {link.label}
              </NavLink>
            ))}
          </nav>
          <div className="flex items-center gap-3 text-sm text-slate-400">
            {user ? (
              <>
                <span className="hidden sm:inline">{user.email}</span>
                <button
                  type="button"
                  onClick={() => {
                    logout();
                    navigate("/login");
                  }}
                  className="btn"
                >
                  Logout
                </button>
              </>
            ) : null}
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}
