import { SUPPORTED_API_VERSION, health, tokenStore } from "../lib/companion";

// Runs every time Spotify starts (a custom app's own code only runs when its page is open).
// Pre-alpha: it only checks that the companion is reachable. The startup sync (roadmap phase 2/3)
// will call POST /sync/start here when the configured interval has elapsed.

(async () => {
  while (!Spicetify?.showNotification) {
    await new Promise((resolve) => setTimeout(resolve, 100));
  }

  // Not paired yet: the user has not set anything up, so stay silent.
  if (!tokenStore.get()) return;

  const info = await health();
  if (!info.ok) {
    console.debug("[ytm-sync] companion not reachable; skipping startup sync");
    return;
  }
  if (info.data.api_version !== SUPPORTED_API_VERSION) {
    console.warn(
      `[ytm-sync] companion API ${info.data.api_version} != expected ${SUPPORTED_API_VERSION}`
    );
  }
})();
