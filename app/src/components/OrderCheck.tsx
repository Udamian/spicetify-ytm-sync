import React from "react";
import styles from "../css/app.module.scss";
import { Bar } from "./Bar";
import { resyncAll } from "../lib/autosync";
import { Key, t } from "../lib/i18n";

type State =
  | { kind: "idle" }
  | { kind: "running"; progress: number }
  | { kind: "done"; moves: number; added: number; verified: boolean }
  | { kind: "failed" };

/**
 * "Check the order now": re-sends the finished copies. The helper app adds anything missing and
 * moves misplaced songs back to Spotify's order, so it also repairs a playlist that drifted.
 */
export function OrderCheck() {
  const [state, setState] = React.useState<State>({ kind: "idle" });

  const run = async () => {
    setState({ kind: "running", progress: 0 });
    try {
      const result = await resyncAll((progress) => setState({ kind: "running", progress }));
      setState({ kind: "done", ...result });
    } catch {
      setState({ kind: "failed" });
    }
  };

  const doneKey = (s: Extract<State, { kind: "done" }>): Key =>
    !s.verified ? "ocNotVerified" : s.moves > 0 || s.added > 0 ? "ocFixed" : "ocAlready";

  return (
    <>
      <div className={styles.row}>
        <button className={styles.linkButton} onClick={run} disabled={state.kind === "running"}>
          {t("ocButton")}
        </button>
      </div>
      <p className={styles.muted}>{t("ocHint")}</p>
      {state.kind === "running" && <Bar value={state.progress} />}
      {state.kind === "done" && (
        <p className={state.verified ? styles.success : styles.warning}>
          {t(doneKey(state), { moves: state.moves, added: state.added })}
        </p>
      )}
      {state.kind === "failed" && <p className={styles.error}>{t("ocFailed")}</p>}
    </>
  );
}
