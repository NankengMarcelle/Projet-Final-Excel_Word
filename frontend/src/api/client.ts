import { hasUnsavedWork } from "./unsavedWorkGuard";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL as string | undefined;

if (!API_BASE_URL) {
  // Fail loudly at load time rather than silently falling back to some hardcoded URL — a
  // missing env var should break the build/boot visibly, not send users to the wrong backend.
  throw new Error(
    "VITE_API_BASE_URL is not set. Define it in your .env file (see .env.example) before running or building the app.",
  );
}



const TOKEN_STORAGE_KEY = "sheetflow_token";
const REFRESH_TOKEN_STORAGE_KEY = "sheetflow_refresh_token";

// "Remember me" decides which storage the tokens land in: localStorage survives closing the
// browser, sessionStorage clears when the tab/browser closes. Both are checked on read since we
// don't track which one was used elsewhere.
export function getToken(): string | null {
  return localStorage.getItem(TOKEN_STORAGE_KEY) ?? sessionStorage.getItem(TOKEN_STORAGE_KEY);
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_TOKEN_STORAGE_KEY) ?? sessionStorage.getItem(REFRESH_TOKEN_STORAGE_KEY);
}

export function setTokens(accessToken: string, refreshToken: string, remember: boolean = true): void {
  const store = remember ? localStorage : sessionStorage;
  const other = remember ? sessionStorage : localStorage;
  store.setItem(TOKEN_STORAGE_KEY, accessToken);
  store.setItem(REFRESH_TOKEN_STORAGE_KEY, refreshToken);
  other.removeItem(TOKEN_STORAGE_KEY);
  other.removeItem(REFRESH_TOKEN_STORAGE_KEY);
}

export function clearTokens(): void {
  localStorage.removeItem(TOKEN_STORAGE_KEY);
  localStorage.removeItem(REFRESH_TOKEN_STORAGE_KEY);
  sessionStorage.removeItem(TOKEN_STORAGE_KEY);
  sessionStorage.removeItem(REFRESH_TOKEN_STORAGE_KEY);
}

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : `Request failed with status ${status}`);
    this.status = status;
    this.detail = detail;
  }
}

type RequestOptions = {
  method?: string;
  body?: BodyInit;
  headers?: Record<string, string>;
  skipJsonContentType?: boolean;
  // Internal — set when retrying a request after a successful token refresh, so a 401 on the
  // retry itself (refresh somehow didn't actually fix things) falls straight through to the
  // expired-session handling below instead of looping.
  _isRetry?: boolean;
};

// Dedupes concurrent refresh attempts: several requests can 401 around the same moment (e.g.
// every worksheet GET firing in parallel when the editor opens), and they'd otherwise each
// independently race to redeem the same refresh token — only the first would succeed server-
// side (refresh tokens are single-use, see backend security.hash_token's docstring), silently
// failing the rest. Every caller within the same refresh window shares this one promise instead.
let refreshPromise: Promise<string | null> | null = null;

async function performRefresh(): Promise<string | null> {
  const refreshToken = getRefreshToken();
  if (!refreshToken) return null;
  try {
    const response = await fetch(`${API_BASE_URL}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!response.ok) return null;
    const tokens = (await response.json()) as { access_token: string; refresh_token: string };
    // Keeps the new pair in whichever storage the old ones were already in, so a "don't remember
    // me" session isn't accidentally promoted to surviving a browser restart just by refreshing.
    const remember = localStorage.getItem(TOKEN_STORAGE_KEY) !== null;
    setTokens(tokens.access_token, tokens.refresh_token, remember);
    return tokens.access_token;
  } catch {
    return null;
  }
}

function refreshAccessToken(): Promise<string | null> {
  if (!refreshPromise) {
    refreshPromise = performRefresh().finally(() => {
      refreshPromise = null;
    });
  }
  return refreshPromise;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = { ...options.headers };
  if (!options.skipJsonContentType) {
    headers["Content-Type"] = headers["Content-Type"] ?? "application/json";
  }
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: options.method ?? "GET",
    headers,
    body: options.body,
  });

  if (response.status === 401 && !options._isRetry) {
    const newAccessToken = await refreshAccessToken();
    if (newAccessToken) {
      return request<T>(path, { ...options, _isRetry: true });
    }
  }

  if (response.status === 401) {
    clearTokens();
    if (window.location.pathname !== "/login") {
      // A blocking native alert, not a toast — this fires from a plain module with no React
      // tree to render into, and the whole point is that the user sees and acknowledges it
      // *before* the redirect below wipes the page out from under them. Confirmed live this
      // session: an edit sitting unsaved in useDebouncedAutosave when the token dies mid-request
      // (e.g. natural expiry during a long editing session) used to just vanish behind a silent
      // instant redirect — same category of "looks fine, then a save is gone" bug as a real one
      // already found and fixed in the autosave hook itself. We can't rescue that save (the
      // token that would authorize resending it is the thing that just failed), but the user
      // should at least know to go check, not find out by surprise later.
      const isFrench = localStorage.getItem("antic_lang") !== "en";
      const message = hasUnsavedWork()
        ? isFrench
          ? "Votre session a expiré. Des modifications récentes n'ont peut-être pas été enregistrées. Vous allez être redirigé vers la page de connexion."
          : "Your session has expired. Some recent changes may not have been saved. You'll be redirected to log in again."
        : isFrench
          ? "Votre session a expiré. Vous allez être redirigé vers la page de connexion."
          : "Your session has expired. You'll be redirected to log in again.";
      window.alert(message);
      window.location.href = "/login";
    }
  }

  if (!response.ok) {
    let detail: unknown;
    try {
      const errorBody = await response.json();
      detail = errorBody.detail ?? errorBody;
    } catch {
      detail = response.statusText;
    }
    throw new ApiError(response.status, detail);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    return (await response.json()) as T;
  }
  return undefined as T;
}

export const apiClient = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body !== undefined ? JSON.stringify(body) : undefined }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PUT", body: body !== undefined ? JSON.stringify(body) : undefined }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PATCH", body: body !== undefined ? JSON.stringify(body) : undefined }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
  postForm: <T>(path: string, form: URLSearchParams | FormData) =>
    request<T>(path, { method: "POST", body: form, skipJsonContentType: true }),
};

export async function fetchBlob(path: string): Promise<{ blob: Blob; filename: string | null }> {
  const token = getToken();
  const headers: Record<string, string> = {};
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  const response = await fetch(`${API_BASE_URL}${path}`, { headers });
  if (!response.ok) {
    let detail: unknown;
    try {
      const errorBody = await response.json();
      detail = errorBody.detail ?? errorBody;
    } catch {
      detail = response.statusText;
    }
    throw new ApiError(response.status, detail);
  }
  const disposition = response.headers.get("content-disposition");
  const match = disposition?.match(/filename="?([^"]+)"?/);
  return { blob: await response.blob(), filename: match?.[1] ?? null };
}
