import React from "react";
import styles from "../css/app.module.scss";
import { AuthStatus, deleteAuth, submitHeaders } from "../lib/companion";
import { Key, t } from "../lib/i18n";

type Message = { kind: "ok" | "error" | "warning"; lines: string[] };

const MISSING_TEXT: Record<string, Key> = {
  cookie: "ytMissingCookie",
  "x-goog-authuser": "ytMissingAuthuser",
  "cookie:__Secure-3PAPISID": "ytMissingSession",
};

/** Friendly explanation of which pieces the pasted text lacks (names only, never values). */
export function describeMissing(missing: string[] | undefined): string[] {
  const lines = [t("ytMissingIntro")];
  for (const name of missing ?? []) {
    const key = MISSING_TEXT[name];
    if (key) lines.push(t(key));
  }
  lines.push(t("ytTryPost"));
  return lines;
}

const STATUS_TEXT: Record<AuthStatus, Key> = {
  ok: "ytConnected",
  not_configured: "ytNotConnected",
  expired: "ytExpired",
  error: "ytError",
};

type Props = { status: AuthStatus; onChanged: () => void };

export function YouTubeAuth({ status, onChanged }: Props) {
  const [raw, setRaw] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [message, setMessage] = React.useState<Message | null>(null);
  const connected = status === "ok";

  const onSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    const result = await submitHeaders(raw);
    setBusy(false);

    if (!result.ok) {
      if (result.code === "missing_headers") {
        return setMessage({ kind: "error", lines: describeMissing(result.details?.missing) });
      }
      return setMessage({ kind: "error", lines: [t("ytGenericError")] });
    }

    if (result.data.status === "ok") {
      setRaw(""); // do not keep the copied session in memory once it is stored
      setMessage({
        kind: result.data.warnings.length ? "warning" : "ok",
        lines: [t("ytSaved"), t("ytClosePrivate"), ...(result.data.warnings.length ? [t("ytWarningNoAuth")] : [])],
      });
      return onChanged();
    }
    setMessage({ kind: "error", lines: [t("ytRejected")] });
  };

  const onDisconnect = async () => {
    if (!window.confirm(t("ytDisconnectAsk"))) return;
    await deleteAuth();
    setMessage(null);
    onChanged();
  };

  return (
    <section className={styles.card}>
      <h2>{t("ytTitle")}</h2>
      <p className={connected ? styles.success : styles.muted}>{t(STATUS_TEXT[status])}</p>

      {status === "expired" && <p className={styles.muted}>{t("ytExpiredHint")}</p>}

      {!connected && (
        <form className={styles.form} onSubmit={onSubmit}>
          <p className={styles.muted}>{t("ytGuideIntro")}</p>
          <ol className={styles.guide}>
            <li>{t("ytStep1")}</li>
            <li>{t("ytStep2")}</li>
            <li>{t("ytStep3")}</li>
            <li>{t("ytStep4")}</li>
          </ol>
          <textarea
            className={styles.textarea}
            value={raw}
            onChange={(e) => setRaw(e.target.value)}
            placeholder={t("ytPlaceholder")}
            rows={5}
            spellCheck={false}
            autoComplete="off"
          />
          <button className={styles.button} type="submit" disabled={busy || !raw.trim()}>
            {busy ? t("ytChecking") : t("ytCheck")}
          </button>
        </form>
      )}

      {message && (
        <div className={message.kind === "ok" ? styles.success : message.kind === "warning" ? styles.warning : styles.error} role="status">
          {message.lines.map((line) => (
            <p key={line}>{line}</p>
          ))}
        </div>
      )}

      {connected && (
        <button className={styles.linkButton} onClick={onDisconnect}>
          {t("ytDisconnect")}
        </button>
      )}
    </section>
  );
}
