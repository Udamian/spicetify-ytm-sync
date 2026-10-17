import React from "react";
import styles from "../css/app.module.scss";

/** Progress bar; `value` is 0..1. */
export function Bar({ value }: { value: number }) {
  const percent = Math.max(0, Math.min(100, Math.round(value * 100)));
  return (
    <div
      className={styles.bar}
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={percent}
    >
      <div className={styles.barFill} style={{ width: `${percent}%` }} />
    </div>
  );
}
