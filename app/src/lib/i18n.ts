// Minimal translations (English and Spanish). Add a language by adding one more table that
// has every key of `en` (the compiler checks it).

const en = {
  appTitle: "YTM Sync",
  appSubtitle: "Keep your Spotify music mirrored on YouTube Music.",

  stepCompanion: "Helper app",
  stepPair: "Pair",
  stepYouTube: "YouTube Music",
  stepPlaylist: "Playlist",

  checking: "Looking for the helper app...",
  retry: "Try again",

  offlineTitle: "The helper app is not running",
  offlineBody:
    "YTM Sync needs a small helper app on this computer to talk to YouTube Music. Start it, then press the button below.",
  offlineHint: "Windows: open the YTM Sync Companion shortcut. A window with a pairing code will appear.",

  versionTitle: "Versions do not match",
  versionBody:
    "The helper app (v{version}) speaks API {api}, but this app expects API {expected}. Update whichever is older.",

  pairTitle: "Pair with the helper app",
  pairBody: "Type the code shown in the helper app window. You only do this once.",
  pairPlaceholder: "XXXXXXXX",
  pairButton: "Pair",
  pairInvalid: "That code is not right.",
  pairExpired: "That code expired. The helper app window shows a new one.",
  pairLocked: "Too many attempts. Wait a minute and try again.",
  pairFailed: "Could not pair. Is the helper app still running?",

  ytTitle: "Connect YouTube Music",
  ytConnected: "Connected to YouTube Music",
  ytNotConnected: "Not connected yet",
  ytExpired: "Your YouTube Music session expired. Connect again.",
  ytError: "Could not check the YouTube Music session. Try again in a moment.",
  ytGuideIntro:
    "YouTube Music has no public login for apps, so you copy one request from your browser. It takes about a minute and the data never leaves this computer.",
  ytStep1: "Open a private (incognito) window and sign in at music.youtube.com.",
  ytStep2:
    "Press F12, open the Network tab, type browse in the filter box, then click anything in the page so a request appears.",
  ytStep3:
    "Right-click that request, choose Copy, then Copy as cURL (or Copy as PowerShell). Any of those works.",
  ytStep4: "Paste it below and press the button.",
  ytPlaceholder: "Paste the copied request here",
  ytCheck: "Check and save",
  ytChecking: "Checking...",
  ytSaved: "Done. YouTube Music is connected.",
  ytClosePrivate: "You can close the private window now. Keep it closed so the session stays valid.",
  ytRejected:
    "Saved, but YouTube Music did not accept it. Sign in again in a private window and copy a fresh request.",
  ytMissingIntro: "That does not look like a request from music.youtube.com while signed in.",
  ytMissingCookie: "The cookie is missing.",
  ytMissingAuthuser: "The x-goog-authuser header is missing.",
  ytMissingSession: "The session cookie is missing: you may not be signed in.",
  ytTryPost: "Copy a POST request (for example browse) from music.youtube.com.",
  ytWarningNoAuth: "No authorization header found. If it does not work, copy a POST request.",
  ytGenericError: "Could not save it. Is the helper app still running?",
  ytDisconnect: "Disconnect",
  ytDisconnectAsk: "This removes the saved YouTube Music session from this computer. Continue?",
  ytReconnect: "Connect again",

  wzSourceTitle: "What do you want to copy?",
  wzLiked: "Liked Songs",
  wzLikedCount: "{n} songs",
  wzPlaylistOption: "A Spotify playlist",
  wzPlaylistPlaceholder: "Paste the playlist link (Share > Copy link to playlist)",
  wzPlaylistBad: "That is not a Spotify playlist link.",
  wzDestTitle: "Where should it go in YouTube Music?",
  wzDestNew: "Create a new playlist",
  wzDestNewDefault: "Spotify mirror",
  wzDestExisting: "Use one of my playlists",
  wzDestNone: "You have no playlists yet.",
  wzDestLoadError: "Could not load your YouTube Music playlists.",
  wzDestCreateError: "Could not create the playlist in YouTube Music.",
  wzDestNotEmpty:
    "This playlist already has {n} songs. New songs go after them, so the order only matches Spotify if the playlist starts empty.",
  wzCheck: "Check and preview",
  wzReading: "Reading your Spotify library... {read} of {total}",
  wzReadError: "Could not read your Spotify library. Try again, or update Spotify and Spicetify.",
  wzNoTracks: "That source has no songs that can be copied.",
  wzPreviewTitle: "Ready to copy",
  wzPreviewBody:
    "{total} songs. {matched} already matched, {search} still to look up on YouTube Music.",
  wzEstimate: "Estimated time: {time}. The helper app does the work, so you can keep using Spotify.",
  wzTimeLess: "less than a minute",
  wzTimeMinutes: "about {n} min",
  wzStart: "Start copying",
  wzBack: "Back",
  wzStartError: "Could not start the copy. Is the helper app still running?",
  wzAlreadyRunning: "A copy was already running. This is its progress.",
  wzRunningTitle: "Copying to YouTube Music",
  wzProgress: "{done} of {total}",
  wzCancel: "Cancel",
  wzDoneTitle: "Copy finished",
  wzDoneAdded: "{added} songs added to YouTube Music.",
  wzDoneMatches: "{ok} matched automatically, {review} to review, {nf} not found.",
  wzOrderOk: "Order checked: it matches Spotify.",
  wzOrderBad: "The order could not be fully checked. Run the copy again to repair it.",
  wzFailedTitle: "The copy stopped",
  wzFailedHint: "Start it again: what is already done is not repeated.",
  wzCancelledTitle: "Copy cancelled",
  wzNew: "Copy something else",

  rvTitle: "Songs to review",
  rvIntro:
    "These songs could not be matched with confidence. Listen to the suggestion and tell me if it is right.",
  rvDoubtful: "Doubtful match",
  rvNotFound: "Not found",
  rvListen: "Listen on YouTube Music",
  rvSearch: "Search on YouTube Music",
  rvAccept: "It is right",
  rvSkip: "Skip it",
  rvPasteLabel: "Paste a YouTube Music or YouTube link",
  rvUse: "Use this",
  rvBadLink: "That does not look like a YouTube link.",
  rvLoadError: "Could not load the list. Is the helper app running?",
  rvSaveError: "Could not save that decision. Try again.",
  rvMore: "Showing the first {n}. Decide these and the rest will appear.",
  rvApply: "Apply {n} decisions to YouTube Music",
  rvApplying: "Updating YouTube Music...",
  rvApplied: "Done. {added} songs added and the order is checked.",
  rvApplyError: "Could not apply the changes. Try again.",
  rvAppliedPartial: "The update did not finish. Try again: what is done is not repeated.",

  autoLabel: "Check for new songs every time Spotify starts",
  autoHint: "New Liked Songs and playlist changes are sent to YouTube Music automatically.",
  autoNotifySending: "YTM Sync: sending {n} new songs to YouTube Music...",
  autoNotifyUpdating: "YTM Sync: updating your playlist copy on YouTube Music...",
  autoNotifyDone: "YTM Sync: {added} songs added to YouTube Music.",
  autoNotifyReview: "YTM Sync: {n} songs need your review.",
  autoNotifyExpired: "YTM Sync: your YouTube Music session expired. Open YTM Sync to reconnect.",
  autoNotifyFailed: "YTM Sync: the update stopped. Open YTM Sync for details.",
} as const;

export type Key = keyof typeof en;
type Table = Record<Key, string>;

const es: Table = {
  appTitle: "YTM Sync",
  appSubtitle: "Mantén tu música de Spotify reflejada en YouTube Music.",

  stepCompanion: "App auxiliar",
  stepPair: "Emparejar",
  stepYouTube: "YouTube Music",
  stepPlaylist: "Playlist",

  checking: "Buscando la app auxiliar...",
  retry: "Reintentar",

  offlineTitle: "La app auxiliar no está en marcha",
  offlineBody:
    "YTM Sync necesita una pequeña app auxiliar en este ordenador para hablar con YouTube Music. Ábrela y pulsa el botón de abajo.",
  offlineHint:
    "Windows: abre el acceso directo YTM Sync Companion. Aparecerá una ventana con un código de emparejamiento.",

  versionTitle: "Las versiones no coinciden",
  versionBody:
    "La app auxiliar (v{version}) usa la API {api}, pero esta app espera la API {expected}. Actualiza la que sea más antigua.",

  pairTitle: "Emparejar con la app auxiliar",
  pairBody: "Escribe el código que aparece en la ventana de la app auxiliar. Solo se hace una vez.",
  pairPlaceholder: "XXXXXXXX",
  pairButton: "Emparejar",
  pairInvalid: "Ese código no es correcto.",
  pairExpired: "Ese código caducó. La ventana de la app auxiliar muestra uno nuevo.",
  pairLocked: "Demasiados intentos. Espera un minuto e inténtalo de nuevo.",
  pairFailed: "No se pudo emparejar. ¿Sigue abierta la app auxiliar?",

  ytTitle: "Conectar YouTube Music",
  ytConnected: "Conectado a YouTube Music",
  ytNotConnected: "Todavía sin conectar",
  ytExpired: "Tu sesión de YouTube Music caducó. Vuelve a conectar.",
  ytError: "No se pudo comprobar la sesión de YouTube Music. Inténtalo de nuevo en un momento.",
  ytGuideIntro:
    "YouTube Music no ofrece inicio de sesión público para apps, así que copias una petición de tu navegador. Lleva un minuto y los datos no salen de este ordenador.",
  ytStep1: "Abre una ventana privada (incógnito) e inicia sesión en music.youtube.com.",
  ytStep2:
    "Pulsa F12, abre la pestaña Red (Network), escribe browse en el filtro y haz clic en cualquier cosa de la página para que aparezca una petición.",
  ytStep3:
    "Haz clic derecho en esa petición, elige Copiar y después Copiar como cURL (o Copiar como PowerShell). Cualquiera sirve.",
  ytStep4: "Pégala aquí abajo y pulsa el botón.",
  ytPlaceholder: "Pega aquí la petición copiada",
  ytCheck: "Comprobar y guardar",
  ytChecking: "Comprobando...",
  ytSaved: "Listo. YouTube Music está conectado.",
  ytClosePrivate:
    "Ya puedes cerrar la ventana privada. Mantenla cerrada para que la sesión siga siendo válida.",
  ytRejected:
    "Se guardó, pero YouTube Music no la aceptó. Inicia sesión otra vez en una ventana privada y copia una petición nueva.",
  ytMissingIntro:
    "Eso no parece una petición de music.youtube.com con la sesión iniciada.",
  ytMissingCookie: "Falta la cookie.",
  ytMissingAuthuser: "Falta la cabecera x-goog-authuser.",
  ytMissingSession: "Falta la cookie de sesión: puede que no hayas iniciado sesión.",
  ytTryPost: "Copia una petición POST (por ejemplo browse) de music.youtube.com.",
  ytWarningNoAuth:
    "No se encontró la cabecera authorization. Si no funciona, copia una petición POST.",
  ytGenericError: "No se pudo guardar. ¿Sigue abierta la app auxiliar?",
  ytDisconnect: "Desconectar",
  ytDisconnectAsk:
    "Esto borra de este ordenador la sesión guardada de YouTube Music. ¿Continuar?",
  ytReconnect: "Conectar de nuevo",

  wzSourceTitle: "¿Qué quieres copiar?",
  wzLiked: "Canciones que te gustan",
  wzLikedCount: "{n} canciones",
  wzPlaylistOption: "Una playlist de Spotify",
  wzPlaylistPlaceholder: "Pega el enlace de la playlist (Compartir > Copiar enlace de la playlist)",
  wzPlaylistBad: "Eso no es un enlace de playlist de Spotify.",
  wzDestTitle: "¿Dónde la guardo en YouTube Music?",
  wzDestNew: "Crear una playlist nueva",
  wzDestNewDefault: "Espejo de Spotify",
  wzDestExisting: "Usar una de mis playlists",
  wzDestNone: "Todavía no tienes playlists.",
  wzDestLoadError: "No se pudieron cargar tus playlists de YouTube Music.",
  wzDestCreateError: "No se pudo crear la playlist en YouTube Music.",
  wzDestNotEmpty:
    "Esta playlist ya tiene {n} canciones. Las nuevas van detrás, así que el orden solo coincidirá con Spotify si la playlist empieza vacía.",
  wzCheck: "Comprobar y previsualizar",
  wzReading: "Leyendo tu biblioteca de Spotify... {read} de {total}",
  wzReadError:
    "No se pudo leer tu biblioteca de Spotify. Inténtalo de nuevo, o actualiza Spotify y Spicetify.",
  wzNoTracks: "Ese origen no tiene canciones que se puedan copiar.",
  wzPreviewTitle: "Listo para copiar",
  wzPreviewBody:
    "{total} canciones. {matched} ya emparejadas, {search} por buscar en YouTube Music.",
  wzEstimate:
    "Tiempo estimado: {time}. La app auxiliar hace el trabajo, así que puedes seguir usando Spotify.",
  wzTimeLess: "menos de un minuto",
  wzTimeMinutes: "unos {n} min",
  wzStart: "Empezar a copiar",
  wzBack: "Atrás",
  wzStartError: "No se pudo iniciar la copia. ¿Sigue abierta la app auxiliar?",
  wzAlreadyRunning: "Ya había una copia en marcha. Este es su progreso.",
  wzRunningTitle: "Copiando a YouTube Music",
  wzProgress: "{done} de {total}",
  wzCancel: "Cancelar",
  wzDoneTitle: "Copia terminada",
  wzDoneAdded: "{added} canciones añadidas a YouTube Music.",
  wzDoneMatches: "{ok} emparejadas automáticamente, {review} por revisar, {nf} sin encontrar.",
  wzOrderOk: "Orden comprobado: coincide con Spotify.",
  wzOrderBad: "No se pudo comprobar del todo el orden. Vuelve a copiar para repararlo.",
  wzFailedTitle: "La copia se detuvo",
  wzFailedHint: "Vuelve a empezar: lo que ya está hecho no se repite.",
  wzCancelledTitle: "Copia cancelada",
  wzNew: "Copiar otra cosa",

  rvTitle: "Canciones por revisar",
  rvIntro:
    "No pude emparejar estas canciones con seguridad. Escucha la sugerencia y dime si es la correcta.",
  rvDoubtful: "Coincidencia dudosa",
  rvNotFound: "No encontrada",
  rvListen: "Escuchar en YouTube Music",
  rvSearch: "Buscar en YouTube Music",
  rvAccept: "Es correcta",
  rvSkip: "Omitir",
  rvPasteLabel: "Pega un enlace de YouTube Music o de YouTube",
  rvUse: "Usar esta",
  rvBadLink: "Eso no parece un enlace de YouTube.",
  rvLoadError: "No se pudo cargar la lista. ¿Está en marcha la app auxiliar?",
  rvSaveError: "No se pudo guardar esa decisión. Inténtalo de nuevo.",
  rvMore: "Se muestran las primeras {n}. Decide estas y aparecerán las demás.",
  rvApply: "Aplicar {n} decisiones a YouTube Music",
  rvApplying: "Actualizando YouTube Music...",
  rvApplied: "Listo. {added} canciones añadidas y el orden comprobado.",
  rvApplyError: "No se pudieron aplicar los cambios. Inténtalo de nuevo.",
  rvAppliedPartial: "La actualización no terminó. Inténtalo otra vez: lo ya hecho no se repite.",

  autoLabel: "Buscar canciones nuevas cada vez que arranque Spotify",
  autoHint:
    "Las canciones nuevas de Me gusta y los cambios de tus playlists se envían solos a YouTube Music.",
  autoNotifySending: "YTM Sync: enviando {n} canciones nuevas a YouTube Music...",
  autoNotifyUpdating: "YTM Sync: actualizando la copia de tu playlist en YouTube Music...",
  autoNotifyDone: "YTM Sync: {added} canciones añadidas a YouTube Music.",
  autoNotifyReview: "YTM Sync: {n} canciones necesitan tu revisión.",
  autoNotifyExpired:
    "YTM Sync: tu sesión de YouTube Music caducó. Abre YTM Sync para volver a conectar.",
  autoNotifyFailed: "YTM Sync: la actualización se detuvo. Abre YTM Sync para ver los detalles.",
};

const tables: Record<"en" | "es", Table> = { en, es };

export function detectLang(): "en" | "es" {
  let locale = "en";
  try {
    locale = Spicetify?.Locale?.getLocale?.() ?? navigator.language ?? "en";
  } catch {
    // Spicetify not ready: fall back to the browser language
    locale = navigator.language ?? "en";
  }
  return locale.toLowerCase().startsWith("es") ? "es" : "en";
}

export function translate(lang: "en" | "es", key: Key, vars: Record<string, string | number> = {}) {
  return tables[lang][key].replace(/\{(\w+)\}/g, (_, name: string) => String(vars[name] ?? ""));
}

export const t = (key: Key, vars?: Record<string, string | number>) =>
  translate(detectLang(), key, vars);
