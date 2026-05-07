import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import {
  ACCESS_TOKEN_KEY,
  REFRESH_TOKEN_KEY,
  apiFetch,
  ApiError,
} from "../api/client";

export type CurrentUser = {
  id: number;
  email: string;
  is_active: boolean;
  is_admin: boolean;
  mfa_enabled: boolean;
};

type AuthContextValue = {
  user: CurrentUser | null;
  isLoading: boolean;
  login: (
    email: string,
    password: string,
    mfaCode?: string,
  ) => Promise<{ mfaRequired: boolean }>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
  refresh: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

type LoginResponse = {
  access_token: string;
  refresh_token: string;
  token_type: string;
  mfa_required: boolean;
};

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  const fetchMe = useCallback(async () => {
    try {
      const me = await apiFetch<CurrentUser>("/api/auth/me");
      setUser(me);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setUser(null);
        localStorage.removeItem(ACCESS_TOKEN_KEY);
        localStorage.removeItem(REFRESH_TOKEN_KEY);
      } else {
        throw error;
      }
    }
  }, []);

  useEffect(() => {
    const token = localStorage.getItem(ACCESS_TOKEN_KEY);
    if (!token) {
      setIsLoading(false);
      return;
    }
    fetchMe()
      .catch(() => {
        setUser(null);
      })
      .finally(() => setIsLoading(false));
  }, [fetchMe]);

  const login = useCallback(
    async (email: string, password: string, mfaCode?: string) => {
      const payload = await apiFetch<LoginResponse>("/api/auth/login", {
        method: "POST",
        body: { email, password, mfa_code: mfaCode },
        skipAuth: true,
      });
      if (payload.mfa_required && !payload.access_token) {
        return { mfaRequired: true };
      }
      localStorage.setItem(ACCESS_TOKEN_KEY, payload.access_token);
      localStorage.setItem(REFRESH_TOKEN_KEY, payload.refresh_token);
      await fetchMe();
      return { mfaRequired: false };
    },
    [fetchMe],
  );

  const register = useCallback(
    async (email: string, password: string) => {
      await apiFetch("/api/auth/register", {
        method: "POST",
        body: { email, password },
        skipAuth: true,
      });
      await login(email, password);
    },
    [login],
  );

  const logout = useCallback(() => {
    localStorage.removeItem(ACCESS_TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
    setUser(null);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ user, isLoading, login, register, logout, refresh: fetchMe }),
    [user, isLoading, login, register, logout, fetchMe],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used inside an AuthProvider");
  }
  return ctx;
}
