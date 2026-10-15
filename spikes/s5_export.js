// Paste this in the Spotify DevTools console (Spicetify). It reads your Liked Songs the way that
// was verified in spike S4 (pages of 500 from offset 0), picks 200 random tracks and copies them
// to the clipboard as JSON. Paste the clipboard into spikes/.s1/tracks.json (git-ignored).
(async () => {
  const N = 200;
  const api = Spicetify.Platform.LibraryAPI;
  const all = [];
  let offset = 0;
  let total = Infinity;
  while (offset < total) {
    const page = await api.getTracks({ limit: 500, offset });
    total = page.totalLength ?? 0;
    console.log(`page offset=${offset}: ${page.items?.length ?? "no items"} items (total ${total})`);
    if (!page.items || page.items.length === 0) break;
    all.push(...page.items);
    offset += page.items.length;
  }
  const usable = all.filter((t) => t && t.uri?.startsWith("spotify:track:") && !t.isLocal);
  console.log(`read ${all.length} rows, ${usable.length} usable`);

  // Fisher-Yates shuffle, then take N.
  for (let i = usable.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [usable[i], usable[j]] = [usable[j], usable[i]];
  }
  const items = usable.slice(0, N).map((t) => ({
    uri: t.uri,
    title: t.name,
    artists: (t.artists || []).map((a) => a.name),
    duration_ms: t.duration?.milliseconds ?? null,
    album: t.album?.name ?? null,
  }));
  if (items.length === 0) {
    console.log("Nothing to export. Send me the 'page offset=' lines printed above.");
    return;
  }
  const text = JSON.stringify(items, null, 1);
  window.__tracks = text; // always kept, in case the clipboard fails
  try {
    copy(text); // DevTools' own copy(): works even when the page is not focused
    console.log(`Copied ${items.length} tracks to the clipboard. Paste them into the file.`);
    return;
  } catch { }
  try {
    await navigator.clipboard.writeText(text);
    console.log(`Copied ${items.length} tracks to the clipboard.`);
    return;
  } catch { }
  console.log(`${items.length} tracks ready. Run:  copy(window.__tracks)`);
})();