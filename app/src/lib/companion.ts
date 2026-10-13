// Client for the local companion service (HTTP contract v1, see companion/README.md).
//
// Plain `fetch` to 127.0.0.1 on purpose: Spicetify.CosmosAsync routes external URLs through a
// third-party CORS proxy, and the companion carries YouTube Music credentials. Whether the
// Spotify web view may call localhost directly is to be confirmed in spike S3.

export const COMPANION_URL = "http://127.0.0.1:48215";
export const SUPPORTED_API_VERSION = 1;

const TOKEN_KEY = "ytm-sync:token";

export type ErrorKind = "offline" | "unauthorized" | "rate_limited" | "rejected" | "server";

export type Result<T> =
  | { ok: true; data: T }
  | { ok: false; error: ErrorKind; status?: number; code?: string };

export type HealthInfo = { ok: boolean; version: string; api_version: number };
export type AuthStatus = "not_configured" | "ok" | "expired" | "error";
export type Playlist = { id: string; title: string; count: number | null };

export const tokenStore = {
  get(): string | null {
    return Spicetify.LocalStorage.get(TOKEN_KEY);
  },
  set(token: string): void {
    Spicetify.LocalStorage.set(TOKEN_KEY, token);
  },
  clear(): void {
    Spicetify.LocalStorage.remove(TOKEN_KEY);
  },
};

async function request<T>(
  path: string,
  options: { method?: string; body?: unknown; auth?: boolean } = {}
): Promise<Result<T>> {
  const headers: Record<string, string> = {};
  if (options.auth) {
    const token = tokenStore.get();
    if (!token) return { ok: false, error: "unauthorized" };
    headers["Authorization"] = `Bearer ${token}`;
  }
  if (options.body !== undefined) headers["Content-Type"] = "application/json";

  let response: Response;
  try {
    response = await fetch(COMPANION_URL + path, {
      method: options.method ?? "GET",
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    });
  } catch {
    return { ok: false, error: "offline" };
  }

  if (response.ok) {
    const data = response.status === 204 ? undefined : await response.json();
    return { ok: true, data: data as T };
  }

  let code: string | undefined;
  try {
    code = (await response.json()).error;
  } catch {
    // Body was not JSON; the status code is all we have.
  }
  const status = response.status;
  if (status === 401) {
    tokenStore.clear(); // token no longer valid: force a new pairing
    return { ok: false, error: "unauthorized", status, code };
  }
  if (status === 429) return { ok: false, error: "rate_limited", status, code };
  if (status >= 500) return { ok: false, error: "server", status, code };
  return { ok: false, error: "rejected", status, code };
}

export const health = () => request<HealthInfo>("/health");

export async function pair(code: string): Promise<Result<void>> {
  const result = await request<{ token: string }>("/pair", { method: "POST", body: { code } });
  if (!result.ok) return result;
  tokenStore.set(result.data.token);
  return { ok: true, data: undefined };
}

export const authStatus = () =>
  request<{ status: AuthStatus }>("/auth/status", { auth: true });

export const submitHeaders = (headers: string) =>
  request<{ status: AuthStatus; warnings: string[] }>("/auth/headers", {
    method: "POST",
    body: { headers },
    auth: true,
  });

export const listPlaylists = () =>
  request<{ playlists: Playlist[] }>("/playlists", { auth: true });
