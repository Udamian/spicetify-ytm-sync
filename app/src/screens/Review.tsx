import React from "react";
import styles from "../css/app.module.scss";
import { Bar } from "../components/Bar";
import { resyncPair, syncedPairs, waitForJob } from "../lib/autosync";
import { ReviewItem, listReview, resolveReview } from "../lib/companion";
import { Key, t } from "../lib/i18n";

// Songs the matcher was not sure about (roadmap phase 3, slice 3). The person listens to the
// suggestion and accepts or skips it, or pastes the right link for a song that was not found.
// A decision only changes the helper app's records; "Apply" re-sends the source so the accepted
// songs are added to YouTube Music at their correct position.

const SHOWN_MAX = 500; // the helper app returns at most this many at a time

/** Video id from a YouTube / YouTube Music link, or the bare 11-character id. */
export function parseVideoId(text: string): string | null {
  const value = text.trim();
  if (/^[A-Za-z0-9_-]{11}$/.test(value)) return value;
  try {
    const url = new URL(value);
    const host = url.hostname.replace(/^www\./, "");
    if (host === "youtu.be") return pick(url.pathname.slice(1));
    if (host === "youtube.com" || host === "music.youtube.com") {
      if (url.pathname === "/watch") return pick(url.searchParams.get("v"));
      const shorts = /^\/(?:shorts|embed)\/([^/?#]+)/.exec(url.pathname);
      if (shorts) return pick(shorts[1]);
    }
  } catch {
    // not a URL
  }
  return null;
}

const pick = (id: string | null) => (id && /^[A-Za-z0-9_-]{11}$/.test(id) ? id : null);

type Props = { refreshKey: number; onAuthLost: () => void };
type Applying = { state: "idle" } | { state: "running"; progress: number } | { state: "done"; added: number } | { state: "failed" };

export function Review({ refreshKey, onAuthLost }: Props) {
  const [items, setItems] = React.useState<ReviewItem[] | null>(null);
  const [loadFailed, setLoadFailed] = React.useState(false);
  const [error, setError] = React.useState<Key | null>(null);
  const [accepted, setAccepted] = React.useState(0);
  const [applying, setApplying] = React.useState<Applying>({ state: "idle" });

  React.useEffect(() => {
    let alive = true;
    (async () => {
      const result = await listReview();
      if (!alive) return;
      if (result.ok) {
        setItems(result.data.items);
        setLoadFailed(false);
      } else if (result.error === "unauthorized") {
        onAuthLost();
      } else {
        setLoadFailed(true);
      }
    })();
    return () => {
      alive = false;
    };
  }, [refreshKey, onAuthLost]);

  const decide = async (item: ReviewItem, videoId: string | null) => {
    setError(null);
    const result = await resolveReview(item.uri, videoId);
    if (!result.ok) {
      if (result.error === "unauthorized") return onAuthLost();
      return setError("rvSaveError");
    }
    setItems((current) => (current ?? []).filter((i) => i.uri !== item.uri));
    if (videoId) setAccepted((n) => n + 1);
  };

  const apply = async () => {
    setError(null);
    setApplying({ state: "running", progress: 0 });
    try {
      const pairs = await syncedPairs();
      if (!pairs || pairs.length === 0) throw new Error("no pairs");
      let added = 0;
      for (const pair of pairs) {
        const started = await resyncPair(pair);
        const jobId =
          started.kind === "started" ? started.jobId : started.kind === "busy" ? started.jobId : undefined;
        if (jobId === undefined) throw new Error("not started");
        const job = await waitForJob(jobId, {
          everyMs: 2000,
          onProgress: (j) => setApplying({ state: "running", progress: j.progress }),
        });
        if (!job || job.state !== "done") throw new Error("not finished");
        added += job.report?.added ?? 0;
      }
      setAccepted(0);
      setApplying({ state: "done", added });
    } catch {
      setApplying({ state: "failed" });
    }
  };

  if (loadFailed) {
    return (
      <section className={styles.card}>
        <h2>{t("rvTitle")}</h2>
        <p className={styles.error}>{t("rvLoadError")}</p>
      </section>
    );
  }
  const showApplyResult = applying.state === "done" || applying.state === "failed";
  if (!items || (items.length === 0 && accepted === 0 && !showApplyResult)) return null;

  return (
    <section className={styles.card}>
      <h2>{t("rvTitle")}</h2>
      {items.length > 0 && <p className={styles.muted}>{t("rvIntro")}</p>}

      {accepted > 0 && applying.state !== "running" && (
        <div className={styles.row}>
          <button className={styles.button} onClick={apply}>
            {t("rvApply", { n: accepted })}
          </button>
        </div>
      )}
      {applying.state === "running" && (
        <>
          <p className={styles.muted}>{t("rvApplying")}</p>
          <Bar value={applying.progress} />
        </>
      )}
      {applying.state === "done" && (
        <p className={styles.success}>{t("rvApplied", { added: applying.added })}</p>
      )}
      {applying.state === "failed" && <p className={styles.error}>{t("rvAppliedPartial")}</p>}
      {error && <p className={styles.error}>{t(error)}</p>}

      <ul className={styles.reviewList}>
        {items.map((item) => (
          <ReviewRow key={item.uri} item={item} onDecide={decide} disabled={applying.state === "running"} />
        ))}
      </ul>
      {items.length >= SHOWN_MAX && <p className={styles.muted}>{t("rvMore", { n: SHOWN_MAX })}</p>}
    </section>
  );
}

function ReviewRow({
  item,
  onDecide,
  disabled,
}: {
  item: ReviewItem;
  onDecide: (item: ReviewItem, videoId: string | null) => void;
  disabled: boolean;
}) {
  const [link, setLink] = React.useState("");
  const [bad, setBad] = React.useState(false);
  const search = `https://music.youtube.com/search?q=${encodeURIComponent(`${item.title} ${item.artists}`)}`;

  const useLink = () => {
    const id = parseVideoId(link);
    if (!id) return setBad(true);
    setBad(false);
    onDecide(item, id);
  };

  return (
    <li className={styles.reviewItem}>
      <div>
        <strong>{item.title}</strong>
        <span className={styles.muted}> · {item.artists}</span>
        <span className={item.status === "review" ? styles.badgeWarn : styles.badgeError}>
          {t(item.status === "review" ? "rvDoubtful" : "rvNotFound")}
        </span>
      </div>
      {item.status === "review" && item.video_id ? (
        <div className={styles.row}>
          <a href={`https://music.youtube.com/watch?v=${item.video_id}`} target="_blank" rel="noreferrer">
            {t("rvListen")}
          </a>
          <button className={styles.smallButton} disabled={disabled} onClick={() => onDecide(item, item.video_id)}>
            {t("rvAccept")}
          </button>
          <button className={styles.linkButton} disabled={disabled} onClick={() => onDecide(item, null)}>
            {t("rvSkip")}
          </button>
        </div>
      ) : (
        <div className={styles.form}>
          <a href={search} target="_blank" rel="noreferrer">
            {t("rvSearch")}
          </a>
          <div className={styles.row}>
            <input
              className={styles.plainInput}
              value={link}
              onChange={(e) => {
                setLink(e.target.value);
                setBad(false);
              }}
              placeholder={t("rvPasteLabel")}
              spellCheck={false}
            />
            <button className={styles.smallButton} disabled={disabled || !link.trim()} onClick={useLink}>
              {t("rvUse")}
            </button>
            <button className={styles.linkButton} disabled={disabled} onClick={() => onDecide(item, null)}>
              {t("rvSkip")}
            </button>
          </div>
          {bad && <p className={styles.error}>{t("rvBadLink")}</p>}
        </div>
      )}
    </li>
  );
}
