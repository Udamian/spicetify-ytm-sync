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
  | { ok: false; error: ErrorKind; status?: number; code?: string; details?: ErrorBody };

/** JSON body of an error answer, e.g. `{error: "missing_headers", missing: ["cookie"]}`. */
export type ErrorBody = { error?: string; missing?: string[]; warnings?: string[]; job_id?: number };

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

  let details: ErrorBody | undefined;
  try {
    details = (await response.json()) as ErrorBody;
  } catch {
    // Body was not JSON; the status code is all we have.
  }
  const code = details?.error;
  const status = response.status;
  if (status === 401) {
    tokenStore.clear(); // token no longer valid: force a new pairing
    return { ok: false, error: "unauthorized", status, code, details };
  }
  if (status === 429) return { ok: false, error: "rate_limited", status, code, details };
  if (status >= 500) return { ok: false, error: "server", status, code, details };
  return { ok: false, error: "rejected", status, code, details };
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

export type SyncTrack = {
  uri: string;
  title: string;
  artists: string[];
  durationMs: number | null;
  album?: string | null;
};
export type SyncKind = "initial_dump" | "incremental";
export type JobState = "queued" | "running" | "done" | "failed" | "cancelled";
export type SyncReport = {
  matched_ok: number;
  to_review: number;
  not_found: number;
  added: number;
  already_present: number;
  duplicates_collapsed: number;
  order_verified: boolean;
  order_moves: number;
};
export type Job = {
  id: number;
  pair_id: number;
  kind: SyncKind;
  state: JobState;
  done: number;
  total: number;
  progress: number;
  error: string | null;
  error_code: string | null;
  report: SyncReport | null;
  created_at: string | null;
  finished_at: string | null;
};
export type ReviewItem = {
  uri: string;
  title: string;
  artists: string;
  duration_ms: number | null;
  status: "review" | "not_found";
  video_id: string | null;
  confidence: number | null;
};

export const previewSync = (tracks: SyncTrack[]) =>
  request<{ total: number; already_matched: number; to_search: number; estimated_seconds: number }>(
    "/sync/preview",
    { method: "POST", body: { tracks }, auth: true }
  );

export const startSync = (args: {
  sourceUri: string;
  destPlaylistId: string;
  kind: SyncKind;
  tracks: SyncTrack[];
}) =>
  request<{ job_id: number | null; pair_id?: number; nothing_to_do?: boolean }>("/sync/start", {
    method: "POST",
    body: {
      source_uri: args.sourceUri,
      dest_playlist_id: args.destPlaylistId,
      kind: args.kind,
      tracks: args.tracks,
    },
    auth: true,
  });

export const cancelSync = (jobId: number) =>
  request<{ cancelled: boolean }>("/sync/cancel", {
    method: "POST",
    body: { job_id: jobId },
    auth: true,
  });

export const syncStatus = () =>
  request<{
    jobs: Job[];
    worker_running: boolean;
    review_count: number;
    not_found_count: number;
  }>("/status", { auth: true });

export const jobStatus = (jobId: number) =>
  request<{ job: Job }>(`/status?job_id=${jobId}`, { auth: true });

export const listReview = () => request<{ items: ReviewItem[] }>("/review", { auth: true });

export const resolveReview = (uri: string, videoId: string | null) =>
  request<{ ok: boolean }>("/review/resolve", {
    method: "POST",
    body: { uri, video_id: videoId },
    auth: true,
  });

export const deleteAuth = () => request<void>("/auth", { method: "DELETE", auth: true });

export const listPlaylists = () =>
  request<{ playlists: Playlist[] }>("/playlists", { auth: true });

export const createPlaylist = (title: string) =>
  request<Playlist>("/playlists", { method: "POST", body: { title }, auth: true });

export type Pair = {
  id: number;
  source_uri: string;
  dest_playlist_id: string;
  mode: "additive" | "mirror";
  last_synced_at: string | null;
  synced_count: number;
};

export const listPairs = () => request<{ pairs: Pair[] }>("/pairs", { auth: true });

/** Spotify URIs of the pair's last completed sync, in Spotify order. */
export const pairSynced = (pairId: number) =>
  request<{ uris: string[] }>(`/pairs/${pairId}/synced`, { auth: true });

/** Resume a failed job with the data the helper app already stored. */
export const retrySync = (jobId: number) =>
  request<{ job_id: number }>("/sync/retry", {
    method: "POST",
    body: { job_id: jobId },
    auth: true,
  });

export type AutostartInfo = { supported: boolean; enabled: boolean };

export const getAutostart = () => request<AutostartInfo>("/autostart", { auth: true });

export const setAutostart = (enabled: boolean) =>
  request<AutostartInfo>("/autostart", { method: "POST", body: { enabled }, auth: true });

/** Summary with no secrets, ids or song titles, meant to be pasted into a bug report. */
export const getDiagnostics = () =>
  request<Record<string, unknown>>("/diagnostics", { auth: true });

/** Stops the helper app (a running copy is paused and resumes the next time it starts). */
export const stopCompanion = () =>
  request<{ ok: boolean }>("/shutdown", { method: "POST", body: {}, auth: true });
