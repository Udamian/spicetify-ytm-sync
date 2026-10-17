import { runStartupSync } from "../lib/startup";

// Runs every time Spotify starts (a custom app's own code only runs while its page is open).
// It sends what is new since the last copy to YouTube Music, through the helper app.

(async () => {
  // Wait until Spotify's internal APIs exist, then give the UI a moment to settle.
  while (!Spicetify?.showNotification || !Spicetify?.Platform?.LibraryAPI) {
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  await new Promise((resolve) => setTimeout(resolve, 4000));

  await runStartupSync((message, isError) => Spicetify.showNotification(message, !!isError, 6000));
})();
