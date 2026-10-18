import { planFor, startPlan, syncedPairs, waitForJob } from "./autosync";
import { SUPPORTED_API_VERSION, authStatus, health, tokenStore } from "./companion";
import { t } from "./i18n";
import { autoSyncSetting } from "./settings";

export type Notify = (message: string, isError?: boolean) => void;

/**
 * The check done every time Spotify starts. Silent unless something is worth saying: it never
 * nags a person who has not set the app up, and a helper app that is simply not running is not
 * an error (the next start will try again).
 */
export async function runStartupSync(notify: Notify): Promise<void> {
  if (!autoSyncSetting.get() || !tokenStore.get()) return;

  const info = await health();
  if (!info.ok || info.data.api_version !== SUPPORTED_API_VERSION) return;

  const auth = await authStatus();
  if (!auth.ok) return;
  if (auth.data.status === "expired") return notify(t("autoNotifyExpired"), true);
  if (auth.data.status !== "ok") return;

  const pairs = await syncedPairs();
  if (!pairs) return;

  for (const pair of pairs) {
    try {
      const plan = await planFor(pair);
      if (!plan) continue;

      notify(
        plan.kind === "incremental"
          ? t("autoNotifySending", { n: plan.tracks.length })
          : t("autoNotifyUpdating")
      );
      const started = await startPlan(pair, plan);
      if (started.kind === "failed") return notify(t("autoNotifyFailed"), true);
      if (started.kind !== "started") continue; // nothing to do, or the app already runs it

      const job = await waitForJob(started.jobId);
      if (!job) continue; // helper app closed: the job resumes the next time it starts
      if (job.state === "failed") {
        return notify(
          t(job.error_code === "session_expired" ? "autoNotifyExpired" : "autoNotifyFailed"),
          true
        );
      }
      if (job.state === "done" && job.report) {
        if (job.report.added > 0) notify(t("autoNotifyDone", { added: job.report.added }));
        if (!job.report.order_verified) notify(t("autoNotifyOrder"), true);
        if (job.report.to_review + job.report.not_found > 0) {
          notify(t("autoNotifyReview", { n: job.report.to_review + job.report.not_found }));
        }
      }
    } catch {
      // Spotify's internal API changed or is not ready: say nothing, try again next start.
      console.debug("[ytm-sync] startup check failed for pair", pair.id);
    }
  }
}
