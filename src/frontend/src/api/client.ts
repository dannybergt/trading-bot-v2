/**
 * Thin fetch wrapper around the backend API.
 *
 * Pulls the access token from localStorage on every request so that token
 * rotation through `AuthContext` propagates immediately. On a 401 the wrapper
 * tries the `/api/auth/refresh` endpoint once and replays the original
 * request; if refresh also fails the caller receives the 401 and
 * `AuthContext` will clear the session.
 */

export const ACCESS_TOKEN_KEY = "access_token";
export const REFRESH_TOKEN_KEY = "refresh_token";

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, message: string, detail: unknown) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

type FetchOptions = Omit<RequestInit, "body" | "headers"> & {
  body?: unknown;
  headers?: Record<string, string>;
  skipAuth?: boolean;
};

async function readResponse(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) {
    return null;
  }
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

async function attemptRefresh(): Promise<boolean> {
  const refresh = localStorage.getItem(REFRESH_TOKEN_KEY);
  if (!refresh) {
    return false;
  }
  try {
    const response = await fetch("/api/auth/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refresh }),
    });
    if (!response.ok) {
      return false;
    }
    const payload = (await response.json()) as {
      access_token?: string;
      refresh_token?: string;
    };
    if (!payload.access_token) {
      return false;
    }
    localStorage.setItem(ACCESS_TOKEN_KEY, payload.access_token);
    if (payload.refresh_token) {
      localStorage.setItem(REFRESH_TOKEN_KEY, payload.refresh_token);
    }
    return true;
  } catch {
    return false;
  }
}

export async function apiFetch<T = unknown>(
  path: string,
  options: FetchOptions = {},
): Promise<T> {
  const { body, headers = {}, skipAuth, ...rest } = options;
  const token = skipAuth ? null : localStorage.getItem(ACCESS_TOKEN_KEY);

  const finalHeaders: Record<string, string> = { ...headers };
  if (body !== undefined && !finalHeaders["Content-Type"]) {
    finalHeaders["Content-Type"] = "application/json";
  }
  if (token) {
    finalHeaders["Authorization"] = `Bearer ${token}`;
  }

  const init: RequestInit = {
    ...rest,
    headers: finalHeaders,
    body: body === undefined ? undefined : JSON.stringify(body),
  };

  let response = await fetch(path, init);
  if (response.status === 401 && !skipAuth) {
    const refreshed = await attemptRefresh();
    if (refreshed) {
      const retryToken = localStorage.getItem(ACCESS_TOKEN_KEY);
      if (retryToken) {
        finalHeaders["Authorization"] = `Bearer ${retryToken}`;
      }
      response = await fetch(path, { ...init, headers: finalHeaders });
    }
  }

  const payload = await readResponse(response);
  if (!response.ok) {
    const detail =
      (payload && typeof payload === "object" && "detail" in payload
        ? (payload as { detail?: unknown }).detail
        : payload) ?? response.statusText;
    throw new ApiError(
      response.status,
      typeof detail === "string" ? detail : `Request failed: ${response.status}`,
      payload,
    );
  }
  return payload as T;
}
