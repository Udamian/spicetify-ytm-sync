// Reads the user's Spotify library through Spicetify's internal APIs (no Spotify Web API:
// it needs Premium and a developer app). These APIs are internal and can change between Spotify
// versions, so everything that touches them lives in this file only.
//
// Verified in spikes S3/S4 (Spotify desktop, October 2026):
//   LibraryAPI.getTracks({limit, offset})       -> {items, totalLength, ...}, newest first
//   PlaylistAPI.getContents(uri, {limit, offset}) -> {items, totalLength, ...}
//   items[]: {uri, name, artists[{name}], album{name}, duration{milliseconds}, isLocal, addedAt}

export const LIKED_SONGS_URI = "spotify:collection:tracks";

/**
 * Accepts what people paste for a playlist: a `spotify:playlist:ID` URI or an
 * `open.spotify.com/playlist/ID` link (optionally with `?si=...`). Returns the URI, or null.
 */
export function parsePlaylistInput(text: string): string | null {
  const value = text.trim();
  const uri = /^spotify:playlist:([A-Za-z0-9]{1,32})$/.exec(value);
  if (uri) return value;
  const link = /^https?:\/\/open\.spotify\.com\/(?:intl-[a-z]+\/)?playlist\/([A-Za-z0-9]{1,32})(?:[/?#].*)?$/.exec(value);
  return link ? `spotify:playlist:${link[1]}` : null;
}

const PAGE_SIZE = 500; // 500 items took ~380 ms in S4
const NEWEST_PAGE_SIZE = 50;

export type SpotifyTrack = {
  uri: string;
  title: string;
  artists: string[];
  durationMs: number | null;
  album: string | null;
  addedAt: string | null; // ISO date; may be null for some playlist items
};

type RawItem = {
  type?: string;
  uri?: string;
  name?: string;
  artists?: { name?: string }[];
  album?: { name?: string };
  duration?: { milliseconds?: number };
  isLocal?: boolean;
  addedAt?: string;
};
type RawPage = { items?: RawItem[]; totalLength?: number };

export class SpotifyReadError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "SpotifyReadError";
  }
}

/** Convert a raw item; returns null for what cannot be synced (local files, episodes...). */
export function toTrack(item: RawItem): SpotifyTrack | null {
  if (!item.uri || !item.uri.startsWith("spotify:track:")) return null;
  if (item.isLocal || (item.type && item.type !== "track")) return null;
  return {
    uri: item.uri,
    title: item.name ?? "",
    artists: (item.artists ?? []).map((a) => a.name ?? "").filter(Boolean),
    durationMs: item.duration?.milliseconds ?? null,
    album: item.album?.name ?? null,
    addedAt: item.addedAt ?? null,
  };
}

type PageFetcher = (offset: number, limit: number) => Promise<RawPage>;

function pageFetcher(sourceUri: string): PageFetcher {
  const platform = Spicetify?.Platform;
  if (sourceUri === LIKED_SONGS_URI) {
    const library = platform?.LibraryAPI;
    if (typeof library?.getTracks !== "function") {
      throw new SpotifyReadError("LibraryAPI.getTracks is not available in this Spotify version");
    }
    return (offset, limit) => library.getTracks({ limit, offset });
  }
  const playlists = platform?.PlaylistAPI;
  if (typeof playlists?.getContents !== "function") {
    throw new SpotifyReadError("PlaylistAPI.getContents is not available in this Spotify version");
  }
  return (offset, limit) => playlists.getContents(sourceUri, { limit, offset });
}

async function fetchPage(fetcher: PageFetcher, offset: number, limit: number): Promise<RawPage> {
  try {
    const page = await fetcher(offset, limit);
    if (!page || !Array.isArray(page.items)) throw new Error("unexpected response shape");
    return page;
  } catch (error) {
    throw new SpotifyReadError(`Could not read Spotify at offset ${offset}: ${String(error)}`);
  }
}

/**
 * Whole source in Spotify's own order (index 0 = first row shown in the Spotify UI).
 * For Liked Songs that is newest first. Duplicated URIs are kept: they are part of the order.
 */
export async function readAll(
  sourceUri: string,
  onProgress?: (read: number, total: number) => void
): Promise<SpotifyTrack[]> {
  const fetcher = pageFetcher(sourceUri);
  const tracks: SpotifyTrack[] = [];
  let offset = 0;
  let total = Infinity;
  while (offset < total) {
    const page = await fetchPage(fetcher, offset, PAGE_SIZE);
    total = page.totalLength ?? offset + page.items!.length;
    for (const item of page.items!) {
      const track = toTrack(item);
      if (track) tracks.push(track);
    }
    if (page.items!.length === 0) break; // defensive: never loop forever
    offset += page.items!.length;
    onProgress?.(Math.min(offset, total), total);
  }
  return tracks;
}

/** Number of rows Spotify reports for the source (cheap: one item). */
export async function readTotal(sourceUri: string): Promise<number> {
  const page = await fetchPage(pageFetcher(sourceUri), 0, 1);
  return page.totalLength ?? page.items!.length;
}

/**
 * Startup check for Liked Songs: reads from the top in small pages and stops at the first track
 * that is already synced. Returns the new tracks in Spotify order (newest first).
 * Only valid for Liked Songs, where new items always appear at the top.
 */
export async function readNewLiked(known: ReadonlySet<string>): Promise<SpotifyTrack[]> {
  const fetcher = pageFetcher(LIKED_SONGS_URI);
  const fresh: SpotifyTrack[] = [];
  for (let offset = 0; ; ) {
    const page = await fetchPage(fetcher, offset, NEWEST_PAGE_SIZE);
    if (page.items!.length === 0) return fresh;
    for (const item of page.items!) {
      const track = toTrack(item);
      if (!track) continue;
      if (known.has(track.uri)) return fresh;
      fresh.push(track);
    }
    offset += page.items!.length;
    if (offset >= (page.totalLength ?? offset)) return fresh;
  }
}
