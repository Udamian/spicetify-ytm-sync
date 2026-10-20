import React from "react";
import styles from "../css/app.module.scss";
import { Bar } from "./Bar";
import {
  AutostartInfo,
  Job,
  getAutostart,
  getDiagnostics,
  health,
  listPairs,
  setAutostart,
  stopCompanion,
  syncStatus,
} from "../lib/companion";
import { Key, t } from "../lib/i18n";
import { runStartupSync } from "../lib/startup";

type Message = { text: Key; vars?: Record<string, string | number>; tone: "ok" | "warn" | "error" };

const POLL_MS = 4000;

/** "5 min ago" style text for an ISO timestamp. */
export function whenText(iso: string | null, now = Date.now()): string {
  const then = iso ? Date.parse(iso) : NaN;
  if (Number.isNaN(then)) return t("pnWhenNow");
  const minutes = Math.max(0, Math.floor((now - then) / 60000));
  if (minutes < 1) return t("pnWhenNow");
  if (minutes < 60) return t("pnWhenMinutes", { n: minutes });
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return t("pnWhenHours", { n: hours });
  return t("pnWhenDays", { n: Math.floor(hours / 24) });
}

const notify = (message: string, isError?: boolean) =>
  Spicetify.showNotification(message, !!isError, 6000);

/**
 * Controls for the helper app, inside the YTM Sync page: what it is doing, "Sync now", the
 * start-with-Windows switch, a diagnostics copy and a way to stop it. A web page cannot start a
 * program, so there is no "Start" button: the helper app starts with Windows or from the Start Menu.
 */
export function CompanionPanel({ onStopped }: { onStopped: () => void }) {
  const [version, setVersion] = React.useState<string | null>(null);
  const [lastSync, setLastSync] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState<Job | null>(null);
  const [autostart, setAutostartInfo] = React.useState<AutostartInfo | null>(null);
  const [syncing, setSyncing] = React.useState(false);
  const [message, setMessage] = React.useState<Message | null>(null);
  const [confirmStop, setConfirmStop] = React.useState(false);
  const [diagText, setDiagText] = React.useState<string | null>(null);
  const alive = React.useRef(true);

  const load = React.useCallback(async () => {
    const [info, pairs, status] = await Promise.all([health(), listPairs(), syncStatus()]);
    if (!alive.current) return;
    if (info.ok) setVersion(info.data.version);
    if (pairs.ok) {
      const dates = pairs.data.pairs.map((p) => p.last_synced_at).filter((d): d is string => !!d);
      setLastSync(dates.sort().pop() ?? null);
    }
    if (status.ok) {
      setBusy(status.data.jobs.find((j) => j.state === "running" || j.state === "queued") ?? null);
    }
  }, []);

  React.useEffect(() => {
    alive.current = true;
    load();
    getAutostart().then((r) => alive.current && r.ok && setAutostartInfo(r.data));
    const timer = window.setInterval(load, POLL_MS);
    return () => {
      alive.current = false;
      window.clearInterval(timer);
    };
  }, [load]);

  const syncNow = async () => {
    setSyncing(true);
    setMessage(null);
    try {
      const outcome = await runStartupSync(notify, { force: true });
      if (outcome.failed) setMessage({ text: "pnSyncFailed", tone: "error" });
      else if (outcome.pairs === 0) setMessage({ text: "pnSyncNoCopies", tone: "warn" });
      else if (outcome.added === 0) setMessage({ text: "pnSyncUpToDate", tone: "ok" });
      else {
        setMessage({
          text: outcome.added === 1 ? "pnSyncSent" : "pnSyncSentMany",
          vars: { n: outcome.added },
          tone: "ok",
        });
      }
    } catch {
      setMessage({ text: "pnSyncFailed", tone: "error" });
    } finally {
      setSyncing(false);
      load();
    }
  };

  const toggleAutostart = async (enabled: boolean) => {
    setMessage(null);
    const result = await setAutostart(enabled);
    if (result.ok) setAutostartInfo(result.data);
    else setMessage({ text: "pnAutostartError", tone: "error" });
  };

  const stop = async () => {
    setConfirmStop(false);
    const result = await stopCompanion();
    if (result.ok) return onStopped();
    setMessage({ text: "pnStopFailed", tone: "error" });
  };

  const copyDiagnostics = async () => {
    setMessage(null);
    setDiagText(null);
    const result = await getDiagnostics();
    if (!result.ok) return setMessage({ text: "pnDiagFailed", tone: "error" });
    const text = JSON.stringify(result.data, null, 2);
    try {
      await navigator.clipboard.writeText(text);
      setMessage({ text: "pnDiagCopied", tone: "ok" });
    } catch {
      // The clipboard can be blocked in Spotify's window: show the text to copy by hand.
      setDiagText(text);
      setMessage({ text: "pnDiagManual", tone: "warn" });
    }
  };

  const tone = { ok: styles.success, warn: styles.warning, error: styles.error };

  return (
    <section className={styles.card}>
      <h2>{t("pnTitle")}</h2>

      <p>
        {version ? t("pnRunning", { version }) : t("checking")}
        {" · "}
        <span className={styles.muted}>
          {lastSync ? t("pnLast", { when: whenText(lastSync) }) : t("pnLastNever")}
        </span>
      </p>

      {busy && (
        <>
          <p className={styles.muted}>{t("pnBusy", { percent: Math.round(busy.progress * 100) })}</p>
          <Bar value={busy.progress} />
        </>
      )}

      <div className={styles.row}>
        <button className={styles.button} onClick={syncNow} disabled={syncing || !!busy}>
          {syncing ? t("pnSyncing") : t("pnSyncNow")}
        </button>
        {!confirmStop && (
          <button className={styles.linkButton} onClick={() => setConfirmStop(true)}>
            {t("pnStop")}
          </button>
        )}
      </div>

      {confirmStop && (
        <>
          <p className={styles.warning}>{t("pnStopAsk")}</p>
          <div className={styles.row}>
            <button className={styles.smallButton} onClick={stop}>
              {t("pnStop")}
            </button>
            <button className={styles.linkButton} onClick={() => setConfirmStop(false)}>
              {t("wzCancel")}
            </button>
          </div>
        </>
      )}

      {autostart?.supported && (
        <>
          <label className={styles.choice}>
            <input
              type="checkbox"
              checked={autostart.enabled}
              onChange={(e) => toggleAutostart(e.target.checked)}
            />
            <span>{t("pnAutostart")}</span>
          </label>
          <p className={styles.muted}>{t("pnAutostartHint")}</p>
        </>
      )}

      <div className={styles.row}>
        <button className={styles.linkButton} onClick={copyDiagnostics}>
          {t("pnDiag")}
        </button>
      </div>
      <p className={styles.muted}>{t("pnDiagHint")}</p>

      {message && <p className={tone[message.tone]}>{t(message.text, message.vars)}</p>}
      {diagText && <textarea className={styles.textarea} readOnly rows={8} value={diagText} />}
    </section>
  );
}
