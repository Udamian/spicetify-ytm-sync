import React from "react";
import styles from "./css/app.module.scss";
import { Stepper, StepId } from "./components/Stepper";
import { Review } from "./screens/Review";
import { Wizard } from "./screens/Wizard";
import { YouTubeAuth } from "./screens/YouTubeAuth";
import {
  AuthStatus,
  HealthInfo,
  SUPPORTED_API_VERSION,
  authStatus,
  health,
  pair,
  tokenStore,
} from "./lib/companion";
import { Key, t } from "./lib/i18n";
import { autoSyncSetting } from "./lib/settings";

// Setup (roadmap phase 3): find the helper app, pair, connect YouTube Music, then the wizard
// that copies the chosen Spotify source to a YouTube Music playlist.

type View =
  | { kind: "checking" }
  | { kind: "offline" }
  | { kind: "incompatible"; info: HealthInfo }
  | { kind: "unpaired"; message?: Key }
  | { kind: "ready"; youtube: AuthStatus };

const PAIR_ERRORS: Record<string, Key> = {
  invalid_code: "pairInvalid",
  expired: "pairExpired",
  locked: "pairLocked",
};

function currentStep(view: View): StepId {
  switch (view.kind) {
    case "checking":
    case "offline":
    case "incompatible":
      return "companion";
    case "unpaired":
      return "pair";
    case "ready":
      return view.youtube === "ok" ? "playlist" : "youtube";
  }
}

function App() {
  const [view, setView] = React.useState<View>({ kind: "checking" });
  const [code, setCode] = React.useState("");
  const [reviewKey, setReviewKey] = React.useState(0);
  const [auto, setAuto] = React.useState(() => autoSyncSetting.get());
  const onFinished = React.useCallback(() => setReviewKey((n) => n + 1), []);

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
    const message: Key =
      (result.code && PAIR_ERRORS[result.code]) ||
      (result.error === "rate_limited" ? "pairLocked" : "pairFailed");
    setView({ kind: "unpaired", message });
  };

  return (
    <div className={styles.container}>
      <h1 className={styles.title}>{t("appTitle")}</h1>
      <p className={styles.subtitle}>{t("appSubtitle")}</p>

      <Stepper current={currentStep(view)} />

      {view.kind === "checking" && <p className={styles.muted}>{t("checking")}</p>}

      {view.kind === "offline" && (
        <section className={styles.card}>
          <h2>{t("offlineTitle")}</h2>
          <p>{t("offlineBody")}</p>
          <p className={styles.muted}>{t("offlineHint")}</p>
          <button className={styles.button} onClick={refresh}>
            {t("retry")}
          </button>
        </section>
      )}

      {view.kind === "incompatible" && (
        <section className={styles.card}>
          <h2>{t("versionTitle")}</h2>
          <p>
            {t("versionBody", {
              version: view.info.version,
              api: view.info.api_version,
              expected: SUPPORTED_API_VERSION,
            })}
          </p>
        </section>
      )}

      {view.kind === "unpaired" && (
        <form className={styles.card} onSubmit={onPair}>
          <h2>{t("pairTitle")}</h2>
          <p>{t("pairBody")}</p>
          <input
            className={styles.input}
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder={t("pairPlaceholder")}
            maxLength={12}
            autoFocus
          />
          <button className={styles.button} type="submit" disabled={!code.trim()}>
            {t("pairButton")}
          </button>
          {view.message && <p className={styles.error}>{t(view.message)}</p>}
        </form>
      )}

      {view.kind === "ready" && <YouTubeAuth status={view.youtube} onChanged={refresh} />}

      {view.kind === "ready" && view.youtube === "ok" && (
        <>
          <Wizard onAuthLost={refresh} onFinished={onFinished} />
          <Review refreshKey={reviewKey} onAuthLost={refresh} />
          <section className={styles.card}>
            <label className={styles.choice}>
              <input
                type="checkbox"
                checked={auto}
                onChange={(e) => {
                  autoSyncSetting.set(e.target.checked);
                  setAuto(e.target.checked);
                }}
              />
              <span>{t("autoLabel")}</span>
            </label>
            <p className={styles.muted}>{t("autoHint")}</p>
          </section>
        </>
      )}
    </div>
  );
}

export default App;
