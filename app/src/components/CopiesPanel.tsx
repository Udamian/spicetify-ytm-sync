import React from "react";
import styles from "../css/app.module.scss";
import { whenText } from "./CompanionPanel";
import { Pair, Playlist, deletePair, listPairs, listPlaylists, setPairActive } from "../lib/companion";
import { Key, t, tn } from "../lib/i18n";
import { LIKED_SONGS_URI } from "../lib/spotify";

type Names = { sources: Record<string, string>; dests: Record<string, string> };
type Problem = { id: number; text: Key };

/** The name Spotify shows for a playlist, or null when Spicetify cannot tell. */
async function playlistName(uri: string): Promise<string | null> {
  try {
    const meta = await Spicetify.Platform?.PlaylistAPI?.getMetadata?.(uri);
    return typeof meta?.name === "string" && meta.name ? meta.name : null;
  } catch {
    return null;
  }
}

/** An old helper app answers 404/405 to what it does not know: say so instead of a vague error. */
function failureText(result: { status?: number }): Key {
  return result.status === 404 || result.status === 405 ? "cpOutdated" : "cpError";
}

/**
 * The copies the helper app keeps up to date: switch one off (skipped at startup and by "check
 * the order") or forget it. Forgetting never deletes anything on YouTube Music or Spotify.
 */
export function CopiesPanel({ refreshKey, onAuthLost }: { refreshKey: number; onAuthLost: () => void }) {
  const [pairs, setPairs] = React.useState<Pair[] | null>(null);
  const [names, setNames] = React.useState<Names>({ sources: {}, dests: {} });
  const [asking, setAsking] = React.useState<number | null>(null);
  const [problem, setProblem] = React.useState<Problem | null>(null);

  const load = React.useCallback(async () => {
    const result = await listPairs();
    if (!result.ok) {
      if (result.error === "unauthorized") onAuthLost();
      return;
    }
    setPairs(result.data.pairs);
    const lists = await listPlaylists();
    const dests: Record<string, string> = {};
    if (lists.ok) lists.data.playlists.forEach((p: Playlist) => (dests[p.id] = p.title));
    const sources: Record<string, string> = {};
    const uris = Array.from(new Set(result.data.pairs.map((p) => p.source_uri)));
    await Promise.all(
      uris
        .filter((uri) => uri !== LIKED_SONGS_URI)
        .map(async (uri) => {
          const name = await playlistName(uri);
          if (name) sources[uri] = name;
        })
    );
    setNames({ sources, dests });
  }, [onAuthLost]);

  React.useEffect(() => {
    load();
  }, [load, refreshKey]);

  const toggle = async (pair: Pair, active: boolean) => {
    setProblem(null);
    const result = await setPairActive(pair.id, active);
    if (result.ok) setPairs((all) => all && all.map((p) => (p.id === pair.id ? { ...p, active } : p)));
    else setProblem({ id: pair.id, text: failureText(result) });
  };

  const forget = async (pair: Pair) => {
    setAsking(null);
    setProblem(null);
    const result = await deletePair(pair.id);
    if (result.ok) return setPairs((all) => all && all.filter((p) => p.id !== pair.id));
    setProblem({
      id: pair.id,
      text: result.code === "already_running" ? "cpRunning" : failureText(result),
    });
  };

  if (!pairs || pairs.length === 0) return null;

  return (
    <section className={styles.card}>
      <h2>{t("cpTitle")}</h2>
      <p className={styles.muted}>{t("cpHint")}</p>
      {pairs.map((pair) => {
        const source =
          pair.source_uri === LIKED_SONGS_URI
            ? t("cpLiked")
            : names.sources[pair.source_uri] ?? t("cpPlaylist");
        const dest = names.dests[pair.dest_playlist_id] ?? pair.dest_playlist_id;
        return (
          <div key={pair.id} className={styles.copyItem}>
            <strong>
              {source} {"→"} {dest}
            </strong>
            <span className={styles.muted}>
              {pair.last_synced_at
                ? t("cpDetail", {
                    count: tn("cpSongs", pair.synced_count, { n: pair.synced_count }),
                    when: whenText(pair.last_synced_at),
                  })
                : t("cpUnfinished")}
            </span>
            <label className={styles.choice}>
              <input
                type="checkbox"
                checked={pair.active !== false}
                onChange={(e) => toggle(pair, e.target.checked)}
              />
              <span>{t("cpActive")}</span>
            </label>
            {pair.active === false && <span className={styles.warning}>{t("cpInactive")}</span>}
            {asking === pair.id ? (
              <>
                <span className={styles.warning}>{t("cpForgetAsk")}</span>
                <div className={styles.row}>
                  <button className={styles.smallButton} onClick={() => forget(pair)}>
                    {t("cpForgetYes")}
                  </button>
                  <button className={styles.linkButton} onClick={() => setAsking(null)}>
                    {t("wzCancel")}
                  </button>
                </div>
              </>
            ) : (
              <div className={styles.row}>
                <button className={styles.linkButton} onClick={() => setAsking(pair.id)}>
                  {t("cpForget")}
                </button>
              </div>
            )}
            {problem?.id === pair.id && <span className={styles.error}>{t(problem.text)}</span>}
          </div>
        );
      })}
    </section>
  );
}
