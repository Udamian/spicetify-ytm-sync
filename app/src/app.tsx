import React from "react";
import styles from "./css/app.module.scss";
import {
  AuthStatus,
  HealthInfo,
  SUPPORTED_API_VERSION,
  authStatus,
  health,
  pair,
  tokenStore,
} from "./lib/companion";

// Pre-alpha: only connection and pairing are wired up. The setup wizard (source, destination,
// dry run, progress) arrives in roadmap phase 3.

type View =
  | { kind: "checking" }
  | { kind: "offline" }
  | { kind: "incompatible"; info: HealthInfo }
  | { kind: "unpaired"; message?: string }
  | { kind: "ready"; youtube: AuthStatus };

const YOUTUBE_LABEL: Record<AuthStatus, string> = {
  not_configured: "Not connected",
  ok: "Connected",
  expired: "Session expired - reconnect",
  error: "Could not check the session",
};

const PAIR_ERRORS: Record<string, string> = {
  invalid_code: "That code is not right.",
  expired: "That code expired. Look at the companion window for the new one.",
  locked: "Too many attempts. Wait a minute and try again.",
};

function App() {
  const [view, setView] = React.useState<View>({ kind: "checking" });
  const [code, setCode] = React.useState("");

  const refresh = React.useCallback(async () => {
    setView({ kind: "checking" });
    const info = await health();
    if (!info.ok) return setView({ kind: "offline" });
    if (info.data.api_version !== SUPPORTED_API_VERSION) {
      return setView({ kind: "incompatible", info: info.data });
    }
    if (!tokenStore.get()) return setView({ kind: "unpaired" });
    const status = await authStatus();
    if (!status.ok) {
      return status.error === "unauthorized"
        ? setView({ kind: "unpaired" })
        : setView({ kind: "offline" });
    }
    setView({ kind: "ready", youtube: status.data.status });
  }, []);

  React.useEffect(() => {
    refresh();
  }, [refresh]);

  const onPair = async (event: React.FormEvent) => {
    event.preventDefault();
    const result = await pair(code);
    if (result.ok) {
      setCode("");
      return refresh();
    }
    const message =
      (result.code && PAIR_ERRORS[result.code]) ||
      (result.error === "rate_limited" ? PAIR_ERRORS.locked : "Could not pair.");
    setView({ kind: "unpaired", message });
  };

  return (
    <div className={styles.container}>
      <h1 className={styles.title}>YTM Sync</h1>
      <p className={styles.subtitle}>Keep a Spotify playlist mirrored on YouTube Music.</p>

      {view.kind === "checking" && <p>Looking for the companion...</p>}

      {view.kind === "offline" && (
        <section className={styles.card}>
          <h2>The companion is not running</h2>
          <p>
            YTM Sync needs a small helper app on this computer. Install and start it, then try
            again. See the project README for instructions.
          </p>
          <button className={styles.button} onClick={refresh}>
            Try again
          </button>
        </section>
      )}

      {view.kind === "incompatible" && (
        <section className={styles.card}>
          <h2>Version mismatch</h2>
          <p>
            The companion (v{view.info.version}) speaks API {view.info.api_version}, but this app
            expects API {SUPPORTED_API_VERSION}. Update whichever is older.
          </p>
        </section>
      )}

      {view.kind === "unpaired" && (
        <form className={styles.card} onSubmit={onPair}>
          <h2>Pair with the companion</h2>
          <p>Enter the code shown in the companion window.</p>
          <input
            className={styles.input}
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="XXXXXXXX"
            autoFocus
          />
          <button className={styles.button} type="submit" disabled={!code.trim()}>
            Pair
          </button>
          {view.message && <p className={styles.error}>{view.message}</p>}
        </form>
      )}

      {view.kind === "ready" && (
        <section className={styles.card}>
          <h2>YouTube Music</h2>
          <p>{YOUTUBE_LABEL[view.youtube]}</p>
          <p className={styles.muted}>The setup wizard is coming soon.</p>
        </section>
      )}
    </div>
  );
}

export default App;
