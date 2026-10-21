import React from "react";
import styles from "../css/app.module.scss";
import {
  Job,
  Playlist,
  SyncTrack,
  cancelSync,
  createPlaylist,
  jobStatus,
  listPlaylists,
  retrySync,
  previewSync,
  startSync,
  syncStatus,
} from "../lib/companion";
import { Bar } from "../components/Bar";
import { Key, t } from "../lib/i18n";
import {
  LIKED_SONGS_URI,
  parsePlaylistInput,
  readAll,
  readTotal,
} from "../lib/spotify";

// Initial dump wizard (roadmap phase 3, slice 2): choose the Spotify source and the YouTube
// Music destination, preview, run the copy with progress. The heavy work happens in the
// helper app; this screen only reads Spotify, sends the tracks and shows the job's progress.

type Destination = { kind: "new"; name: string } | { kind: "existing"; playlist: Playlist };
type Preview = { total: number; already_matched: number; to_search: number; estimated_seconds: number };

type Phase =
  | { kind: "setup" }
  | { kind: "reading"; read: number; total: number }
  | { kind: "preview"; sourceUri: string; tracks: SyncTrack[]; preview: Preview; dest: Destination }
  | { kind: "starting" }
  | { kind: "interrupted"; job: Job }
  | { kind: "running"; jobId: number; resumed: boolean }
  | { kind: "finished"; job: Job };

const POLL_MS = 2000;
const ACTIVE = new Set(["queued", "running"]);
// Failures worth offering "Resume" for. `internal_error` is a bug: resuming would just repeat it.
const RESUMABLE = new Set(["session_expired", "write_failed", "sync_error"]);

export function formatEstimate(seconds: number): string {
  if (seconds < 60) return t("wzTimeLess");
  return t("wzTimeMinutes", { n: Math.round(seconds / 60) });
}

type Props = { onAuthLost: () => void; onFinished?: () => void };

export function Wizard({ onAuthLost, onFinished }: Props) {
  const [phase, setPhase] = React.useState<Phase>({ kind: "setup" });
  const [liveJob, setLiveJob] = React.useState<Job | null>(null);
  const [error, setError] = React.useState<Key | null>(null);

  // setup form
  const [sourceKind, setSourceKind] = React.useState<"liked" | "playlist">("liked");
  const [playlistText, setPlaylistText] = React.useState("");
  const [destKind, setDestKind] = React.useState<"new" | "existing">("new");
  const [newName, setNewName] = React.useState(() => t("wzDestNewDefault"));
  const [existingId, setExistingId] = React.useState("");
  const [playlists, setPlaylists] = React.useState<Playlist[] | null>(null);
  const [likedTotal, setLikedTotal] = React.useState<number | null>(null);
  const [destLoadFailed, setDestLoadFailed] = React.useState(false);

  // A playlist created for this copy is remembered, so retrying "Start" never creates a second one.
  const created = React.useRef<Playlist | null>(null);

  React.useEffect(() => {
    let alive = true;
    (async () => {
      // A copy may already be running (the user left the app and came back).
      const status = await syncStatus();
      if (!alive) return;
      if (!status.ok && status.error === "unauthorized") return onAuthLost();
      if (status.ok) {
        const active = status.data.jobs.find((job) => ACTIVE.has(job.state));
        if (active) return setPhase({ kind: "running", jobId: active.id, resumed: true });
        const last = status.data.jobs[0]; // newest first
        if (last?.state === "failed" && last.error_code && RESUMABLE.has(last.error_code)) {
          return setPhase({ kind: "interrupted", job: last });
        }
      }
      const lists = await listPlaylists();
      if (!alive) return;
      if (lists.ok) setPlaylists(lists.data.playlists);
      else setDestLoadFailed(true);
      try {
        // Right after Spotify starts the library may still be loading and report 0: ask again
        // for a few seconds rather than show a wrong "0 songs".
        for (let attempt = 0; attempt < 5 && alive; attempt++) {
          const total = await readTotal(LIKED_SONGS_URI);
          if (total > 0) {
            setLikedTotal(total);
            break;
          }
          await new Promise((resolve) => setTimeout(resolve, 2000));
        }
      } catch {
        // The count is only a nicety.
      }
    })();
    return () => {
      alive = false;
    };
  }, [onAuthLost]);

  // Progress polling
  React.useEffect(() => {
    if (phase.kind !== "running") return;
    let alive = true;
    const tick = async () => {
      const result = await jobStatus(phase.jobId);
      if (!alive) return;
      if (!result.ok) {
        if (result.error === "unauthorized") onAuthLost();
        return; // transient (helper app busy or restarting): try again on the next tick
      }
      const job = result.data.job;
      if (ACTIVE.has(job.state)) {
        setLiveJob(job);
      } else {
        setPhase({ kind: "finished", job });
        onFinished?.();
      }
    };
    tick();
    const timer = window.setInterval(tick, POLL_MS);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, [phase, onAuthLost, onFinished]);

  const destination = (): Destination | null => {
    if (destKind === "new") return newName.trim() ? { kind: "new", name: newName.trim() } : null;
    const playlist = playlists?.find((p) => p.id === existingId);
    return playlist ? { kind: "existing", playlist } : null;
  };

  const sourceUri = (): string | null =>
    sourceKind === "liked" ? LIKED_SONGS_URI : parsePlaylistInput(playlistText);

  const canCheck =
    (sourceKind === "liked" || playlistText.trim() !== "") && destination() !== null;

  const onCheck = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    const uri = sourceUri();
    const dest = destination();
    if (!uri) return setError("wzPlaylistBad");
    if (!dest) return;

    setPhase({ kind: "reading", read: 0, total: 0 });
    let tracks: SyncTrack[];
    try {
      const read = await readAll(uri, (done, total) =>
        setPhase({ kind: "reading", read: done, total })
      );
      tracks = read.map((track) => ({
        uri: track.uri,
        title: track.title,
        artists: track.artists,
        durationMs: track.durationMs,
        album: track.album,
      }));
    } catch {
      setPhase({ kind: "setup" });
      return setError("wzReadError");
    }
    if (tracks.length === 0) {
      setPhase({ kind: "setup" });
      return setError("wzNoTracks");
    }
    const result = await previewSync(tracks);
    if (!result.ok) {
      setPhase({ kind: "setup" });
      if (result.error === "unauthorized") return onAuthLost();
      return setError(result.code === "bad_tracks" ? "wzBadTracks" : "wzStartError");
    }
    setPhase({ kind: "preview", sourceUri: uri, tracks, preview: result.data, dest });
  };

  const onStart = async () => {
    if (phase.kind !== "preview") return;
    const { sourceUri: uri, tracks, dest } = phase;
    setError(null);
    setPhase({ kind: "starting" });

    let destId: string;
    if (dest.kind === "existing") {
      destId = dest.playlist.id;
    } else {
      if (!created.current) {
        const made = await createPlaylist(dest.name);
        if (!made.ok) {
          setPhase(phase);
          if (made.error === "unauthorized") return onAuthLost();
          return setError("wzDestCreateError");
        }
        created.current = made.data;
      }
      destId = created.current.id;
    }

    const started = await startSync({
      sourceUri: uri,
      destPlaylistId: destId,
      kind: "initial_dump",
      tracks,
    });
    if (started.ok && started.data.job_id !== null) {
      setLiveJob(null);
      return setPhase({ kind: "running", jobId: started.data.job_id, resumed: false });
    }
    if (!started.ok && started.code === "already_running" && started.details?.job_id) {
      setLiveJob(null);
      return setPhase({ kind: "running", jobId: started.details.job_id, resumed: true });
    }
    setPhase(phase);
    if (!started.ok && started.error === "unauthorized") return onAuthLost();
    setError("wzStartError");
  };

  const onCancel = async () => {
    if (phase.kind === "running") await cancelSync(phase.jobId);
  };

  const onResume = async (job: Job) => {
    setError(null);
    const result = await retrySync(job.id);
    if (result.ok) {
      setLiveJob(null);
      return setPhase({ kind: "running", jobId: result.data.job_id, resumed: false });
    }
    if (result.error === "unauthorized") return onAuthLost();
    setError("wzResumeError");
  };

  const reset = () => {
    created.current = null;
    setError(null);
    setPhase({ kind: "setup" });
  };

  // ---- views ---------------------------------------------------------------------------

  if (phase.kind === "reading") {
    return (
      <section className={styles.card}>
        <h2>{t("wzSourceTitle")}</h2>
        <p className={styles.muted}>
          {t("wzReading", { read: phase.read, total: phase.total || "…" })}
        </p>
        <Bar value={phase.total ? phase.read / phase.total : 0} />
      </section>
    );
  }

  if (phase.kind === "preview" || phase.kind === "starting") {
    const shown = phase.kind === "preview" ? phase : null;
    return (
      <section className={styles.card}>
        <h2>{t("wzPreviewTitle")}</h2>
        {shown && (
          <>
            <p>
              {t("wzPreviewBody", {
                total: shown.preview.total,
                matched: shown.preview.already_matched,
                search: shown.preview.to_search,
              })}
            </p>
            <p className={styles.muted}>
              {t("wzEstimate", { time: formatEstimate(shown.preview.estimated_seconds) })}
            </p>
          </>
        )}
        {error && <p className={styles.error}>{t(error)}</p>}
        <div className={styles.row}>
          <button className={styles.button} onClick={onStart} disabled={!shown}>
            {t("wzStart")}
          </button>
          <button className={styles.linkButton} onClick={reset} disabled={!shown}>
            {t("wzBack")}
          </button>
        </div>
      </section>
    );
  }

  if (phase.kind === "running") {
    return (
      <section className={styles.card}>
        <h2>{t("wzRunningTitle")}</h2>
        {phase.resumed && <p className={styles.muted}>{t("wzAlreadyRunning")}</p>}
        <Bar value={liveJob?.progress ?? 0} />
        <p className={styles.muted}>
          {t("wzProgress", { done: liveJob?.done ?? 0, total: liveJob?.total ?? "…" })}
        </p>
        <button className={styles.linkButton} onClick={onCancel}>
          {t("wzCancel")}
        </button>
      </section>
    );
  }

  if (phase.kind === "interrupted") {
    return (
      <section className={styles.card}>
        <h2>{t("wzResumeTitle")}</h2>
        <p>
          {t(phase.job.error_code === "session_expired" ? "wzResumeExpired" : "wzResumeFailed")}
        </p>
        {error && <p className={styles.error}>{t(error)}</p>}
        <div className={styles.row}>
          <button className={styles.button} onClick={() => onResume(phase.job)}>
            {t("wzResume")}
          </button>
          <button className={styles.linkButton} onClick={reset}>
            {t("wzNew")}
          </button>
        </div>
      </section>
    );
  }

  if (phase.kind === "finished") {
    return <Finished job={phase.job} onNew={reset} onResume={onResume} error={error} />;
  }

  // setup
  return (
    <form className={styles.card} onSubmit={onCheck}>
      <h2>{t("wzSourceTitle")}</h2>
      <div className={styles.form}>
        <label className={styles.choice}>
          <input
            type="radio"
            name="source"
            checked={sourceKind === "liked"}
            onChange={() => setSourceKind("liked")}
          />
          <span>
            {t("wzLiked")}
            {likedTotal !== null && (
              <span className={styles.muted}> · {t("wzLikedCount", { n: likedTotal })}</span>
            )}
          </span>
        </label>
        <label className={styles.choice}>
          <input
            type="radio"
            name="source"
            checked={sourceKind === "playlist"}
            onChange={() => setSourceKind("playlist")}
          />
          <span>{t("wzPlaylistOption")}</span>
        </label>
        {sourceKind === "playlist" && (
          <input
            className={styles.plainInput}
            value={playlistText}
            onChange={(e) => setPlaylistText(e.target.value)}
            placeholder={t("wzPlaylistPlaceholder")}
            spellCheck={false}
          />
        )}
      </div>

      <h2>{t("wzDestTitle")}</h2>
      <div className={styles.form}>
        <label className={styles.choice}>
          <input
            type="radio"
            name="dest"
            checked={destKind === "new"}
            onChange={() => setDestKind("new")}
          />
          <span>{t("wzDestNew")}</span>
        </label>
        {destKind === "new" && (
          <input
            className={styles.plainInput}
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            maxLength={150}
          />
        )}
        <label className={styles.choice}>
          <input
            type="radio"
            name="dest"
            checked={destKind === "existing"}
            onChange={() => setDestKind("existing")}
          />
          <span>{t("wzDestExisting")}</span>
        </label>
        {destKind === "existing" && (
          <>
            {destLoadFailed && <p className={styles.error}>{t("wzDestLoadError")}</p>}
            {playlists && playlists.length === 0 && (
              <p className={styles.muted}>{t("wzDestNone")}</p>
            )}
            {playlists && playlists.length > 0 && (
              <select
                className={styles.plainInput}
                value={existingId}
                onChange={(e) => setExistingId(e.target.value)}
              >
                <option value="" />
                {playlists.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.title}
                    {p.count ? ` (${p.count})` : ""}
                  </option>
                ))}
              </select>
            )}
            {(playlists?.find((p) => p.id === existingId)?.count ?? 0) > 0 && (
              <p className={styles.warning}>
                {t("wzDestNotEmpty", {
                  n: playlists?.find((p) => p.id === existingId)?.count ?? 0,
                })}
              </p>
            )}
          </>
        )}
      </div>

      {error && <p className={styles.error}>{t(error)}</p>}
      <button className={styles.button} type="submit" disabled={!canCheck}>
        {t("wzCheck")}
      </button>
    </form>
  );
}

function Finished({
  job,
  onNew,
  onResume,
  error,
}: {
  job: Job;
  onNew: () => void;
  onResume: (job: Job) => void;
  error: Key | null;
}) {
  if (job.state === "cancelled") {
    return (
      <section className={styles.card}>
        <h2>{t("wzCancelledTitle")}</h2>
        <p className={styles.muted}>{t("wzFailedHint")}</p>
        <button className={styles.button} onClick={onNew}>
          {t("wzNew")}
        </button>
      </section>
    );
  }
  if (job.state === "failed" || !job.report) {
    return (
      <section className={styles.card}>
        <h2>{t("wzFailedTitle")}</h2>
        {job.error && <p className={styles.error}>{job.error}</p>}
        <p className={styles.muted}>{t("wzFailedHint")}</p>
        {error && <p className={styles.error}>{t(error)}</p>}
        <div className={styles.row}>
          {job.error_code && RESUMABLE.has(job.error_code) && (
            <button className={styles.button} onClick={() => onResume(job)}>
              {t("wzResume")}
            </button>
          )}
          <button className={job.error_code && RESUMABLE.has(job.error_code) ? styles.linkButton : styles.button} onClick={onNew}>
            {t("wzNew")}
          </button>
        </div>
      </section>
    );
  }
  const report = job.report;
  return (
    <section className={styles.card}>
      <h2>{t("wzDoneTitle")}</h2>
      <p className={styles.success}>{t("wzDoneAdded", { added: report.added })}</p>
      <p>
        {t("wzDoneMatches", {
          ok: report.matched_ok,
          review: report.to_review,
          nf: report.not_found,
        })}
      </p>
      <p className={report.order_verified ? styles.muted : styles.warning}>
        {t(report.order_verified ? "wzOrderOk" : "wzOrderBad")}
      </p>
      <button className={styles.button} onClick={onNew}>
        {t("wzNew")}
      </button>
    </section>
  );
}
