import { planFor, startPlan, syncedPairs, waitForJob } from "./autosync";
import { SUPPORTED_API_VERSION, authStatus, health, tokenStore } from "./companion";
import { t, tn } from "./i18n";
import { autoSyncSetting } from "./settings";

export type Notify = (message: string, isError?: boolean) => void;

export type SyncOutcome = {
  /** Copies that were checked (0 when the helper app, YouTube Music or a copy is missing). */
  pairs: number;
  /** Songs sent to YouTube Music. */
  added: number;
  failed: boolean;
};

/**
 * The check done every time Spotify starts, and by the "Sync now" button (`force`, which
 * ignores the "check at startup" switch). Silent unless something is worth saying: it never
 * nags a person who has not set the app up, and a helper app that is simply not running is not
 * an error (the next start will try again).
 */
export async function runStartupSync(
  notify: Notify,
  options: { force?: boolean } = {}
): Promise<SyncOutcome> {
  const outcome: SyncOutcome = { pairs: 0, added: 0, failed: false };
  if ((!options.force && !autoSyncSetting.get()) || !tokenStore.get()) return outcome;

  const info = await health();
  if (!info.ok || info.data.api_version !== SUPPORTED_API_VERSION) return outcome;

  const auth = await authStatus();
  if (!auth.ok) return outcome;
  if (auth.data.status === "expired") {
    notify(t("autoNotifyExpired"), true);
    return { ...outcome, failed: true };
  }
  if (auth.data.status !== "ok") return outcome;

  const pairs = await syncedPairs();
  if (!pairs) return outcome;
  outcome.pairs = pairs.length;

  for (const pair of pairs) {
    try {
      const plan = await planFor(pair);
      if (!plan) continue;

      notify(
        plan.kind === "incremental"
          ? tn("autoNotifySending", plan.tracks.length, { n: plan.tracks.length })
          : t("autoNotifyUpdating")
      );
      const started = await startPlan(pair, plan);
      if (started.kind === "failed") {
        notify(t("autoNotifyFailed"), true);
        return { ...outcome, failed: true };
      }
      if (started.kind !== "started") continue; // nothing to do, or the app already runs it

      const job = await waitForJob(started.jobId);
      if (!job) continue; // helper app closed: the job resumes the next time it starts
      if (job.state === "failed") {
        notify(
          t(job.error_code === "session_expired" ? "autoNotifyExpired" : "autoNotifyFailed"),
          true
        );
        return { ...outcome, failed: true };
      }
      if (job.state === "done" && job.report) {
        outcome.added += job.report.added;
        if (job.report.added > 0) {
          notify(tn("autoNotifyDone", job.report.added, { added: job.report.added }));
        }
        if (!job.report.order_verified) notify(t("autoNotifyOrder"), true);
        const doubtful = job.report.to_review + job.report.not_found;
        if (doubtful > 0) notify(tn("autoNotifyReview", doubtful, { n: doubtful }));
      }
    } catch {
      // Spotify's internal API changed or is not ready: say nothing, try again next start.
      console.debug("[ytm-sync] startup check failed for pair", pair.id);
      outcome.failed = true;
    }
  }
  return outcome;
}
