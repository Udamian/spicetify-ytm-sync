import {
  Job,
  Pair,
  SyncKind,
  SyncTrack,
  jobStatus,
  listPairs,
  pairSynced,
  startSync,
} from "./companion";
import { LIKED_SONGS_URI, SpotifyTrack, readAll, readNewLiked } from "./spotify";

// Keeping a finished copy up to date. Used by the startup extension and by the review screen
// ("apply my decisions"). The helper app does the heavy work; this only decides *what* to send.

export type Plan = { kind: SyncKind; tracks: SyncTrack[] };

const toSyncTrack = (track: SpotifyTrack): SyncTrack => ({
  uri: track.uri,
  title: track.title,
  artists: track.artists,
  durationMs: track.durationMs,
  album: track.album,
});

/**
 * What a pair needs, or null when it is up to date.
 *  - Liked Songs: new likes sit at the top, so read from the top until a known track appears
 *    and send only those (incremental, added on top in the right order).
 *  - A playlist: new songs can appear anywhere, so compare the whole list with the last
 *    synced one and, if it differs, send it all again. That is cheap, because the helper app
 *    skips tracks it already matched and only adds what is missing and repairs the order.
 */
export async function planFor(pair: Pair): Promise<Plan | null> {
  const synced = await pairSynced(pair.id);
  if (!synced.ok) throw new Error("synced list unavailable");

  if (pair.source_uri === LIKED_SONGS_URI) {
    const fresh = await readNewLiked(new Set(synced.data.uris));
    return fresh.length ? { kind: "incremental", tracks: fresh.map(toSyncTrack) } : null;
  }

  const all = await readAll(pair.source_uri);
  const same =
    all.length === synced.data.uris.length && all.every((t, i) => t.uri === synced.data.uris[i]);
  return same ? null : { kind: "initial_dump", tracks: all.map(toSyncTrack) };
}

/**
 * Pairs that finished their first copy (an unfinished first copy is the wizard's job) and that
 * the person has not switched off.
 */
export async function syncedPairs(): Promise<Pair[] | null> {
  const result = await listPairs();
  if (!result.ok) return null;
  // `active` is missing from an older helper app: only an explicit `false` switches a copy off.
  return result.data.pairs.filter(
    (p) => p.active !== false && p.last_synced_at && p.mode === "additive"
  );
}

export type Started =
  | { kind: "started"; jobId: number }
  | { kind: "nothing" }
  | { kind: "busy"; jobId?: number }
  | { kind: "failed" };

export async function startPlan(pair: Pair, plan: Plan): Promise<Started> {
  const result = await startSync({
    sourceUri: pair.source_uri,
    destPlaylistId: pair.dest_playlist_id,
    kind: plan.kind,
    tracks: plan.tracks,
  });
  if (result.ok) {
    return result.data.job_id === null
      ? { kind: "nothing" }
      : { kind: "started", jobId: result.data.job_id };
  }
  if (result.code === "already_running") return { kind: "busy", jobId: result.details?.job_id };
  return { kind: "failed" };
}

/** Re-send a whole source so decisions taken in the review list reach YouTube Music. */
export async function resyncPair(pair: Pair): Promise<Started> {
  const all = await readAll(pair.source_uri);
  return startPlan(pair, { kind: "initial_dump", tracks: all.map(toSyncTrack) });
}

const FINISHED = new Set(["done", "failed", "cancelled"]);

/**
 * Poll a job until it ends. Returns null when the helper app stays unreachable (it was closed)
 * or when `maxMs` passes; the job itself keeps going in the helper app either way.
 */
export async function waitForJob(
  jobId: number,
  options: { everyMs?: number; maxMs?: number; onProgress?: (job: Job) => void } = {}
): Promise<Job | null> {
  const everyMs = options.everyMs ?? 3000;
  const deadline = Date.now() + (options.maxMs ?? 6 * 60 * 60 * 1000);
  let misses = 0;
  while (Date.now() < deadline) {
    const result = await jobStatus(jobId);
    if (result.ok) {
      misses = 0;
      if (FINISHED.has(result.data.job.state)) return result.data.job;
      options.onProgress?.(result.data.job);
    } else if (result.error === "unauthorized" || ++misses >= 20) {
      return null;
    }
    await new Promise((resolve) => setTimeout(resolve, everyMs));
  }
  return null;
}

export type ResyncResult = { added: number; moves: number; verified: boolean };

/**
 * Re-send every finished pair and wait for it. The helper app adds what is missing and moves
 * misplaced songs into the order Spotify has. Throws when something does not finish.
 */
export async function resyncAll(onProgress?: (progress: number) => void): Promise<ResyncResult> {
  const pairs = await syncedPairs();
  if (!pairs || pairs.length === 0) throw new Error("no pairs");
  const total: ResyncResult = { added: 0, moves: 0, verified: true };
  for (const [index, pair] of pairs.entries()) {
    const started = await resyncPair(pair);
    const jobId =
      started.kind === "started" || started.kind === "busy" ? started.jobId : undefined;
    if (jobId === undefined) throw new Error("not started");
    const job = await waitForJob(jobId, {
      everyMs: 2000,
      onProgress: (j) => onProgress?.((index + j.progress) / pairs.length),
    });
    if (!job || job.state !== "done" || !job.report) throw new Error("not finished");
    total.added += job.report.added;
    total.moves += job.report.order_moves;
    total.verified = total.verified && job.report.order_verified;
  }
  return total;
}
