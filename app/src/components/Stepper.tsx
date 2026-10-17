import React from "react";
import styles from "../css/app.module.scss";
import { t } from "../lib/i18n";

export type StepId = "companion" | "pair" | "youtube" | "playlist";
const ORDER: StepId[] = ["companion", "pair", "youtube", "playlist"];
const LABEL = {
  companion: "stepCompanion",
  pair: "stepPair",
  youtube: "stepYouTube",
  playlist: "stepPlaylist",
} as const;

/** Where the user is in the setup: finished steps are checked, the current one is highlighted. */
export function Stepper({ current }: { current: StepId }) {
  const currentIndex = ORDER.indexOf(current);
  return (
    <ol className={styles.steps} aria-label="Setup progress">
      {ORDER.map((id, index) => {
        const state = index < currentIndex ? "done" : index === currentIndex ? "current" : "todo";
        return (
          <li
            key={id}
            className={`${styles.step} ${styles[`step_${state}`]}`}
            aria-current={state === "current" ? "step" : undefined}
          >
            <span className={styles.stepDot}>{state === "done" ? "✓" : index + 1}</span>
            <span>{t(LABEL[id])}</span>
          </li>
        );
      })}
    </ol>
  );
}
