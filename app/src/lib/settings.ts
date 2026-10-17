// Per-user preferences shared by the app and the startup extension. Both run in the same
// Spotify web view, so Spicetify's LocalStorage is visible to each of them.

const AUTO_SYNC_KEY = "ytm-sync:auto";

export const autoSyncSetting = {
  /** On unless the user turned it off. */
  get(): boolean {
    try {
      return Spicetify.LocalStorage.get(AUTO_SYNC_KEY) !== "0";
    } catch {
      return true;
    }
  },
  set(enabled: boolean): void {
    try {
      Spicetify.LocalStorage.set(AUTO_SYNC_KEY, enabled ? "1" : "0");
    } catch {
      // Storage unavailable: the setting simply does not persist.
    }
  },
};
