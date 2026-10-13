# Spicetify → YouTube Music Sync
## Estudio de viabilidad, barreras y hoja de ruta

Fecha: 12 oct 2026 · Basado en fuentes consultadas hoy (listadas al final). Lo marcado **(a validar)** no lo he podido confirmar y se resuelve en la Fase 0.

---

## 1. Veredicto

**Es viable. Con una decisión de arquitectura obligada y un punto débil conocido.**

| Pregunta | Respuesta corta |
|---|---|
| ¿Es técnicamente posible? | Sí. Tu prototipo ya demuestra extracción, búsqueda, inserción y detección de likes. |
| ¿Se puede publicar en el marketplace de Spicetify? | Sí, pero el marketplace solo distribuye el `.js` de la extensión. El backend Python **no puede viajar dentro**: hay que distribuir un *companion* aparte y guiar su instalación desde la propia extensión. |
| ¿Puede ser "todo por interfaz"? | Casi todo sí (elegir origen/destino, volcado, progreso, ajustes). **Lo único que no se puede hacer realmente cómodo es conectar la cuenta de YouTube Music.** |
| ¿Es estable a largo plazo? | No está garantizado: depende de APIs no oficiales (YT Music vía `ytmusicapi`) y de APIs internas de Spotify. Hay que diseñar para fallar con elegancia y asumir mantenimiento continuo. |

**Recomendación:** seguir adelante, pero empezar por una Fase 0 corta de pruebas (*spikes*) que valide tres puntos go/no-go antes de invertir en la interfaz: (1) cuánto dura la sesión de YT Music, (2) que las escrituras funcionan con la versión actual de `ytmusicapi`, (3) que el companion se puede empaquetar sin que Windows/antivirus lo bloqueen.

---

## 2. Qué tienes ya y qué falta

| Área | Prototipo actual | Necesario para un producto público |
|---|---|---|
| Extracción Spotify | `LibraryAPI.getTracks` / `_collection` | Cualquier playlist (no solo Liked), con orden y fecha de alta; tolerar cambios de API entre versiones de Spotify |
| Estado / duplicados | `LocalStorage` (`ytmusic_synced_uris`) | Mover a una BD del companion: el LocalStorage de Spotify puede perderse al limpiar caché o reinstalar |
| Backend | Flask en `127.0.0.1:5005` con `CORS(app)` | CORS restringido, token de emparejamiento, puerto configurable, instalador |
| Auth YT Music | `browser.json` pegado a mano | Asistente guiado, validador de cabeceras, detección de caducidad |
| Inserción | `search` + `add_playlist_items` uno a uno, pausa 0,35 s | Matching con puntuación, lotes, cola persistente, reintentos |
| Orden | `reversed()` o ordenar a mano en la web | Orden automático (añadir + `moveItem` / `addToTop`) |
| Interfaz | DevTools / consola | Asistente, panel de estado, ajustes, mensajes de error claros |

---

## 3. Hallazgos de la investigación

### 3.1 OAuth de `ytmusicapi` no es una opción
- Desde noviembre de 2024 exige un Client ID/Secret propios de Google Cloud.
- Desde el 29 de agosto de 2025 las llamadas con OAuth a los endpoints de YT Music devuelven HTTP 400. El mantenedor no ve camino de arreglo y en agosto de 2026 la issue sigue activa en la última versión (1.12.2). El workaround recomendado es la autenticación por navegador.
- Aunque funcionara: una app de Google sin verificar queda limitada a 100 usuarios y los scopes de YouTube con datos de usuario son "sensibles" (requieren verificación).
- **Conclusión:** la única vía realista es autenticar con cabeceras/cookies de sesión del navegador (lo que ya haces).

### 3.2 Las cookies caducan antes de lo que dice la documentación
- La documentación de `ytmusicapi` habla de ~2 años salvo que cierres sesión.
- En la práctica, Google **rota las cookies de las sesiones activas**. Si copias las cabeceras de tu navegador de uso diario, esa copia puede morir en horas. Si las capturas en una **ventana de incógnito que luego cierras**, suelen durar semanas (lo documentan Crossfadarr, Music Assistant y yt-dlp; otra herramienta (`ytm`) habla de rotación diaria y caducidad de unas semanas).
- En Windows, Chrome/Edge/Brave cifran las cookies con *App-Bound Encryption* (Chrome 127+), de modo que ningún programa externo puede leerlas. Solo Firefox o el pegado manual funcionan. **Autoextraer cookies del navegador no es fiable.**

### 3.3 Riesgo en las escrituras
- En la issue #813 hay reportes con `ytmusicapi` 1.11.x de errores 401/400 al **crear playlists y añadir canciones** con autenticación por navegador, atribuidos a un cambio en el formato de la cabecera `Authorization` (variantes SAPISID/SAPISID1P/SAPISID3P con sufijo `_u`). No he podido confirmar si está corregido en 1.12.x **(a validar)**. Tu prototipo funciona hoy, buena señal, pero hay que fijar versión y tener un test de humo.

### 3.4 Marketplace de Spicetify
- Requisitos (wiki actualizada el 24 jul 2026): repositorio público en GitHub, topic `spicetify-extensions` y `manifest.json` en la raíz.
- Campos obligatorios del manifest: `name`, `description`, `preview`, `main`, `readme`. Opcionales: `branch`, `authors`, `tags`. `main` apunta a **un único `.js`**.
- El contenido es de la comunidad y no está validado por Spicetify; si se reporta algo malicioso lo excluyen. Una extensión que maneja credenciales de Google tiene que ser transparente y de código abierto.
- Spicetify está activo (última versión que vi: v2.44.0, 5 jul 2026, compatible con Spotify hasta 1.2.93). Pero su documentación avisa de que `Spicetify.Platform` son APIs internas, sin garantía de estabilidad.

### 3.5 Red y CORS dentro de Spotify
- Desde Spicetify 2.32.1, las peticiones de `CosmosAsync` a URLs externas (salvo `api.spotify.com`, `spclient.wg.spotify.com` y `sp://`) se redirigen a un **proxy CORS de Spicetify**.
- Mandar cookies de Google por un proxy de terceros no es aceptable → un cliente 100 % JS hablando con YT Music se descarta como diseño por defecto.
- Para hablar con el companion usa `fetch` directo a `127.0.0.1` (como tu prototipo) y no `CosmosAsync` **(a validar en spike S3)**.

### 3.6 Límites de YouTube Music
- Varias fuentes coinciden en un máximo de **5.000 elementos por playlist**. La lista "Me gusta" de YT Music es un caso especial (~10.000 desde 2023). Si tu origen supera 5.000, el destino no podrá contenerlo.
- `add_playlist_items` con `duplicates=False` hace que **falle el lote entero** si hay un duplicado.
- `edit_playlist` ofrece `moveItem` (tupla `setVideoId`, `setVideoId` sucesor) y `addToTop`. `get_playlist` devuelve el `setVideoId` de cada ítem, necesario para mover o borrar.

### 3.7 Trabajos previos
En mi búsqueda aparecen scripts que copian Liked Songs de Spotify a una playlist de YT Music (YTMusicify, Spotify2YoutubeMusic) y migradores de un solo uso (Stym, LinkList). Todos son CLI/web externos; **no encontré una extensión de Spicetify con interfaz integrada y sincronización continua** (búsqueda no exhaustiva). Hay hueco, y además confirma que la autenticación y el mantenimiento son el dolor común.

---

## 4. Arquitectura recomendada

```
Spotify + Spicetify                        Tu PC                                 Internet
┌─────────────────────────┐  HTTP local  ┌─────────────────────────────┐  HTTPS  ┌───────────────┐
│ Extensión (.js)         │ ───────────▶ │ Companion (Python)          │ ──────▶ │ YouTube Music │
│ · asistente y panel     │ ◀─────────── │ · ytmusicapi                │ ◀────── │ (API no       │
│ · lee playlists Spotify │  token de    │ · SQLite (estado y mapeo)   │         │  oficial)     │
│ · dispara y muestra sync│  emparejado  │ · cola de trabajos, matching│         └───────────────┘
└─────────────────────────┘              └─────────────────────────────┘
```

| Opción | Descripción | Veredicto |
|---|---|---|
| **A. Companion local + extensión** | Lo de arriba | **Recomendada** |
| B. Todo en JS dentro de Spotify | Sin backend | Descartada: CORS, cookies y proxy de terceros |
| C. YouTube Data API v3 (OAuth) | Inserción con posición nativa; búsqueda con `ytmusicapi` sin autenticar | Plan B para uso personal: cuotas por proyecto (la cuota por defecto es baja, **a validar**) y límite de 100 usuarios sin verificar |
| D. Servidor en la nube | Tú alojas el backend | Descartada: custodiarías cookies de Google de otras personas |

### Seguridad del servidor local (obligatorio antes de publicar)
Con `CORS(app)` abierto, **cualquier página web que abras en tu navegador normal podría hacer peticiones a `127.0.0.1:5005` y manejar tu cuenta de YT Music**. Es lo primero a corregir:

1. Escuchar solo en `127.0.0.1`; puerto configurable con fallback si está ocupado.
2. Permitir solo el origen del cliente de Spotify (compruébalo con `location.origin` en DevTools).
3. Token de emparejamiento: el companion lo genera al primer arranque y la extensión lo envía en cada petición.
4. Validar la cabecera `Host` (protege contra *DNS rebinding*).
5. Guardar credenciales con permisos `0600` o con el almacén de claves del SO (`keyring`); nunca en logs.
6. Handshake de versión de API entre extensión y companion.

### Distribución del companion
- **Windows:** ejecutable con PyInstaller o instalador. Sin firma de código, SmartScreen avisa y algunos antivirus suelen marcar los ejecutables de PyInstaller.
- **macOS:** Gatekeeper; la notarización requiere cuenta de desarrollador de pago.
- **Linux:** `pipx`, AppImage o paquete.
- **Medio plazo:** binario único en Go/Rust. Existe un port en Rust de `ytmusicapi` (auth por cookies, añadir/quitar/mover en playlists), pero es joven y, en la versión que vi, aún sin búsqueda.
- La extensión debe detectar "companion no instalado / no está corriendo" y mostrar un botón de descarga con instrucciones.

---

## 5. Diseño de sincronización

**Principios:** (1) Spotify es la fuente de verdad y el destino es un espejo. (2) El orden canónico es el visible en Spotify. (3) Todo es idempotente: relanzar nunca duplica. (4) El estado vive en la BD del companion.

### Datos
- `track_map`: `spotify_uri → videoId, setVideoId, confianza, estado` (ok / no encontrado / revisar).
- `pairs`: playlist origen, playlist destino, instantánea del último orden (lista de URIs), última sincronización.

### Volcado inicial
1. Leer la lista completa de Spotify en orden.
2. Emparejar cada pista con un `videoId`.
3. Escribir en YT Music en lotes.

Para el orden hay dos caminos equivalentes **(a validar en S2)**: activar `addToTop` en el destino y añadir de la más antigua a la más nueva (es tu `reversed(tracks)`), o añadir en el orden visible y activar `addToTop` después para las altas futuras.

### Sincronización incremental (al arrancar Spotify)
- Leer la cabecera de la lista (total + primeros N) y compararla con la instantánea guardada.
- Si cambió, calcular el diff: altas / bajas / movimientos. En Liked Songs el caso típico es "n canciones nuevas arriba".
- Playlists con orden manual: calcular la subsecuencia común más larga entre el orden actual del destino y el deseado, y mover solo el resto con `moveItem` (1 llamada por movimiento). Si hay demasiados movimientos, ofrecer "reconstruir la playlist" como acción explícita, nunca en silencio.

### Calidad del emparejamiento
No quedarse con el primer resultado. Puntuar título normalizado, artistas, duración (tolerancia pequeña) y álbum; penalizar versiones *live*, *remix* o *cover* si el título de origen no las incluye. Por debajo del umbral, la pista pasa a una lista **"Revisar"** visible en la interfaz. Ignorar y listar archivos locales, episodios de podcast y pistas no disponibles.

### Otras reglas
- **Duplicados:** dedupe local antes de enviar. Si dos pistas de Spotify resuelven al mismo `videoId`, conservar la primera y avisar.
- **Bajas en Spotify:** por defecto no se borra en el destino (modo aditivo). Modo espejo opcional, con confirmación y tope de seguridad.
- **Cola persistente y reanudable:** si cierras Spotify a mitad, continúa después.
- **Límite de 5.000:** avisar antes del volcado y ofrecer parar en 5.000 o crear una "Parte 2".
- **Frecuencia:** sincronizar al arrancar si han pasado ≥ X horas (por defecto 12, configurable), botón "Sincronizar ahora" y, opcionalmente, gancho al dar like con *debounce*. Solo corre con Spotify abierto; hay que decirlo en el README.
- **Lectura de Spotify:** además de `LibraryAPI`, evaluar el endpoint oficial de playlists con el token de `Spicetify.Platform.Session` (a través de `CosmosAsync`) como alternativa menos frágil.

### Sobre la caducidad de la sesión (tu duda)
Sincronizar menos veces **no alarga** la sesión: la caducidad la decide Google al rotar cookies. Lo que sí ayuda:
- Capturar las cabeceras desde incógnito o un perfil dedicado que no vuelvas a usar.
- Comprobar si el companion puede guardar las cookies renovadas que devuelve YT Music **(hipótesis, spike S1)**.
- Un chequeo de salud de la sesión al arrancar (una llamada autenticada barata) y, si falla, un aviso claro con botón "Reconectar" **antes** de intentar sincronizar.

---

## 6. Experiencia de usuario

### Asistente de primera vez
1. **Bienvenida y requisitos:** ¿companion detectado y versión compatible?
2. **Conectar YouTube Music:** ver "Autenticación amigable" abajo.
3. **Elegir origen:** Liked Songs o una de tus playlists.
4. **Elegir destino:** una playlist existente de YT Music o crear una nueva. Si no está vacía, preguntar: combinar / reemplazar / nueva.
5. **Vista previa (*dry-run*):** nº de pistas, tiempo estimado, cuántas no se encontraron y cuántas piden revisión.
6. **Volcado con progreso** (consulta periódica a `/status`) y pantalla final con ajustes.

Errores en lenguaje humano: "La sesión de YouTube Music ha caducado → Reconectar", "No encuentro el companion → Descargar".

### Autenticación amigable (escalera de opciones)
| Nivel | Opción | Comentario |
|---|---|---|
| 1 | **Guiado manual** (Fase 4a) | Pantalla con pasos y capturas: abrir YT Music en incógnito, F12 → Network → copiar cabeceras de una petición POST, pegar en un cuadro. El companion valida y dice exactamente qué falta (`cookie`, `x-goog-authuser`, `authorization`). |
| 2 | **Extensión de navegador auxiliar** (Fase 4b, opcional) | Botón "Conectar" que lee la sesión desde dentro del navegador y la envía al companion por localhost. Ya existen exportadores de cabeceras de terceros en la Chrome Web Store (el patrón funciona), pero implica publicar y mantener otra extensión y pasar revisión por el permiso de cookies. |
| ✗ | Leer cookies del navegador desde el companion | Roto en Chrome/Edge/Brave sobre Windows y sospechoso para antivirus. |
| ✗ | Login en ventana embebida | Google bloquea el inicio de sesión en navegadores embebidos **(a validar)**. |

### Dentro de Spotify
`Spicetify.Topbar.Button` + `Spicetify.PopupModal` + `Spicetify.ReactComponent` (Toggle, Button…) + `Spicetify.showNotification`. Desarrollar con **Spicetify Creator** (TypeScript) y publicar el bundle `.js` único.

---

## 7. Matriz de barreras y riesgos

| ID | Barrera | Prob. | Impacto | Mitigación |
|---|---|---|---|---|
| B1 | Autenticación YT Music (OAuth roto, cookies que rotan) | Alta | Alto | Captura en incógnito, validador, chequeo de salud, flujo "Reconectar", spike S1 |
| B2 | Distribución del backend (solo se publica el `.js`; SmartScreen/Gatekeeper/antivirus) | Alta | Alto | Companion con instalador, guía en la extensión, spike S6; valorar firma de código |
| B3 | API no oficial de YT Music puede romper o cambiar (401/400 en escrituras) | Media-Alta | Alto | Fijar versión de `ytmusicapi`, test de humo antes de cada release, mensaje de "servicio no disponible" sin romper nada |
| B4 | APIs internas de Spotify/Spicetify inestables | Alta | Medio | Capa de adaptación aislada, detección de versión, degradar con aviso, seguir las releases de Spicetify |
| B5 | Servidor local expuesto (CORS abierto) | Alta en el prototipo | Alto | Medidas de la sección 4 (fácil de corregir) |
| B6 | Emparejamiento incorrecto de canciones | Alta | Medio | Puntuación, lista "Revisar", caché de mapeos, tasa medida en spike S5 |
| B7 | Orden: muchas llamadas para reordenar | Media | Medio | Subsecuencia común más larga, `addToTop`, confirmación si hay muchos movimientos |
| B8 | Límite de 5.000 por playlist / Liked Songs enormes | Media | Medio | Aviso previo, parar en 5.000 o "Parte 2" |
| B9 | Rate limits (429/400) | Media | Bajo | Lotes, pausas con *backoff*, reanudar |
| B10 | Solo sincroniza con Spotify abierto | Cierta | Bajo | Documentarlo; sync al arrancar + botón manual |
| B11 | Términos de servicio: `ytmusicapi` es no oficial y Spicetify modifica el cliente | Baja-Media | Alto | Bajo volumen, solo local, aviso claro en el README. Revisa los términos de ambos servicios (esto no es asesoramiento legal) |
| B12 | Mantenimiento a largo plazo (una sola persona) | Alta | Alto | Alcance acotado, tests con respuestas grabadas, checklist de release, aceptar contribuciones |
| B13 | Confianza: manejas cookies de Google | Media | Alto | Código abierto, sin telemetría, documentar qué se guarda y dónde, botón "Borrar credenciales" |
| B14 | Plataformas (Windows / macOS / Linux, Spotify de Microsoft Store) | Media | Medio | Decidir soporte inicial (ver sección 9) |

---

## 8. Hoja de ruta

Estimación orientativa para una persona a tiempo parcial (~8-10 h/semana). Total aproximado: **3-4 meses** hasta la publicación.

| Fase | Duración | Entregable | Criterio de salida |
|---|---|---|---|
| **0. Spikes de validación** | 1-2 sem | Notas con resultados de S1-S6 (abajo) | Go/no-go: sesión ≥ 7 días con el método de captura, escrituras OK, acierto de matching aceptable, companion empaquetable |
| **1. Companion sólido** | 2-3 sem | Servidor refactorizado: SQLite, cola de trabajos, token de emparejamiento, CORS restringido, endpoints (`/health`, `/auth`, `/playlists`, `/sync/preview`, `/sync/start`, `/status`), logs sin secretos, tests con `ytmusicapi` simulado | Tests verdes; sin `CORS(app)` abierto |
| **2. Motor de sincronización** | 3 sem | Matching con puntuación, volcado ordenado, diff incremental, reordenado, dedupe, *dry-run*, reanudación, política de borrado | Volcado de 1.000+ pistas con orden idéntico verificado por script |
| **3. Interfaz de la extensión** | 3 sem | Asistente de 6 pasos, botón en la barra superior, panel de estado, errores claros, i18n ES/EN, Spicetify Creator | Flujo completo sin tocar DevTools ni consola |
| **4. Autenticación amigable** | 1-2 sem (en paralelo) | 4a: guía + validador. 4b (opcional): extensión de navegador auxiliar | Un usuario nuevo conecta su cuenta sin ayuda |
| **5. Empaquetado y distribución** | 2 sem | Instalador/ejecutable, bandeja, arranque automático, actualización, GitHub Releases, README con GIFs, repo con topic y `manifest.json`, matriz de compatibilidad extensión ↔ companion | Instalación en una máquina limpia en < 5 min |
| **6. Beta cerrada** | 2 sem | 5-10 testers con distintos SO y tamaños de biblioteca | Sin bugs bloqueantes; tasa de errores de auth conocida |
| **7. Publicación y mantenimiento** | continuo | Anuncio en Discord/Reddit de Spicetify; vigilar releases de Spicetify y `ytmusicapi` | Plan de mantenimiento escrito |

### Fase 0: spikes en detalle
| Spike | Qué probar | Decide |
|---|---|---|
| **S1** Durabilidad de sesión | Capturar cabeceras en incógnito y hacer una llamada autenticada a 1 h, 24 h, 7 d, 14 d, 30 d. Probar también persistir las cookies renovadas | Si la auth por cabeceras es defendible como producto |
| **S2** Escrituras | Con `ytmusicapi` actual: `add_playlist_items` en lotes (¿qué tamaño?), `edit_playlist` con `addToTop` y `moveItem`; comprobar que no hay 401/400 | Estrategia de orden y viabilidad de escribir |
| **S3** Localhost desde Spicetify | Confirmar origen real, `fetch` a `127.0.0.1` permitido, y que `CosmosAsync` no sirve para esto | Diseño de comunicación |
| **S4** Lectura de playlists | Leer una playlist arbitraria con orden y fecha de alta, con 5.000+ pistas; comparar `LibraryAPI` con el endpoint oficial | Capa de lectura |
| **S5** Matching | 200 canciones propias: % correctas, falsas coincidencias, no encontradas | Umbrales y alcance de la lista "Revisar" |
| **S6** Empaquetado | PyInstaller en un Windows limpio: ¿SmartScreen? ¿antivirus? (y macOS si te interesa) | Estrategia de distribución |

---

## 9. Decisiones abiertas (tuyas)

1. **Sistemas operativos soportados al inicio.** Windows primero reduce el trabajo (macOS exige notarización).
2. **Alcance:** ¿solo Liked Songs o cualquier playlist? (Tus requisitos hablan de "playlist a elegir"; la Fase 2 ya lo asume.)
3. **Bajas:** ¿modo aditivo por defecto y espejo opcional?
4. **Licencia** (MIT/GPL) y nombre del proyecto.
5. **Lenguaje del companion:** Python ahora; ¿reescritura a Go/Rust más adelante?
6. **Extensión de navegador auxiliar:** ¿entra en la v1 o queda para la v2?

---

## 10. Siguiente paso concreto

Esta semana, **solo S1 y S2**. S1 necesita días de espera, así que conviene lanzarlo ya: captura las cabeceras en una ventana de incógnito, ciérrala, y programa una llamada autenticada (p. ej. `get_library_playlists`) a 1 h, 24 h, 7 d, 14 d y 30 d. Mientras corre, haz S2 y corrige el `CORS(app)` del prototipo (es rápido y elimina el riesgo B5).

---

## Fuentes

- ytmusicapi, OAuth: https://ytmusicapi.readthedocs.io/en/latest/setup/oauth.html
- ytmusicapi, autenticación por navegador: https://ytmusicapi.readthedocs.io/en/stable/setup/browser.html
- ytmusicapi, issue #813 (OAuth y escrituras): https://github.com/sigma67/ytmusicapi/issues/813
- ytmusicapi, API de playlists: https://ytmusicapi.readthedocs.io/en/stable/reference/playlists.html
- Crossfadarr, rotación de cookies: https://github.com/crossfadarr/crossfadarr
- Music Assistant, cookies de YT Music: https://music-assistant.io/music-providers/youtube-music/
- yt-dlp, issue #8227: https://github.com/yt-dlp/yt-dlp/issues/8227
- `ytm` (App-Bound Encryption y caducidad): https://pypi.org/project/ytm/
- Marketplace de Spicetify, publicación: https://github.com/spicetify/marketplace/wiki/Publishing-to-Marketplace
- Spicetify, extensiones: https://spicetify.app/docs/development/extensions
- Spicetify, `Platform`: https://spicetify.app/docs/development/api-wrapper/methods/platform
- Spicetify CLI v2.32.1 (proxy CORS): https://github.com/spicetify/spicetify-cli/releases/tag/v2.32.1
- Spicetify CLI v2.44.0: https://newreleases.io/project/github/spicetify/cli/release/v2.44.0
- Google, apps sin verificar: https://support.google.com/cloud/answer/7454865?hl=es
- Límite de 5.000 en playlists: https://www.androidcentral.com/youtube-music-liked-songs-problem
- Chrome App-Bound Encryption: https://alternativeto.net/news/2024/8/google-enhances-chrome-security-on-windows-with-app-bound-encryption-to-fight-cookie-theft
- Trabajos previos: https://github.com/itisFarzin/YTMusicify · https://github.com/mahdi-y/Spotify2YoutubeMusic
- Crate Rust `ytmusicapi`: https://docs.rs/crate/ytmusicapi/0.4.0
