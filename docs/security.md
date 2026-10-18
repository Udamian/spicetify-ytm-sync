# Security and threat model

## What is at stake

The companion stores a copy of the user's **YouTube Music browser session** (cookies and request
headers) and listens on a local port. Whoever gets that session can act as the user on that
account, so the main job is making sure nothing but the YTM Sync app can reach the companion.

## Threats and mitigations

| Threat | Mitigation | Code |
|---|---|---|
| **A web page the user visits calls `127.0.0.1`** and drives the account | `Origin` allow-list (default: the Spotify web view only), bearer token on every sensitive endpoint, no wildcard CORS | `app.py`, `security.py` |
| **DNS rebinding**: a hostile domain resolves to `127.0.0.1` | `Host` header must be `127.0.0.1:<port>` or `localhost:<port>` | `security.host_allowed` |
| **Another local process** reads the port | Bearer token stored `0600`; compared in constant time. This does **not** defend against a process running as the same user, which can read the files anyway | `security.TokenStore` |
| **Guessing the pairing code** | One-time 8-hex code, expires after 10 minutes, rotates after every use, locks out for 60 s after 5 failures. `/pair` also requires a browser `Origin` | `security.Pairing` |
| **Pairing code on disk** (background mode has no console to show it) | `pairing-code.json` in the data folder, created `0600` like the token, removed on a clean stop, replaced after every use or expiry. A process of the same user could already read the stored YouTube Music session, so this adds no new reach; other users and web pages cannot read it | `runtime.publish_code` |
| **Anything but the owner stopping the service** | `POST /shutdown` needs the bearer token like every sensitive endpoint; `stop` reads the token from the user's own data folder. No process is ever killed by PID | `app.py`, `runtime.request_shutdown` |
| **Credentials leaking through logs or errors** | Header *values* are never logged or returned; errors name only the missing header; upstream failures return a generic `youtube_error`; `HeaderCheck.__repr__` hides the headers | `headers.py`, `app.py` |
| **Credentials committed by mistake** | `.gitignore` covers `browser.json`, `headers.txt`, `.env`, `spikes/.s1/` | `.gitignore` |
| **Exposure on the network** | Binds to `127.0.0.1` only | `config.HOST` |
| **Oversized request bodies** | 256 KB limit | `app.MAX_BODY_BYTES` |

## Known limits

- The session itself is only as safe as the user's machine. Anything running as the same OS user
  can read `browser.json`.
- Header-based authentication is a workaround, not a supported Google API. Google may rotate or
  invalidate the session at any time (see the study, section 3.2); the app must tell the user
  when to reconnect.
- The default `Origin` of the Spotify web view is **unconfirmed** (spike S3). If it is wrong the
  app simply cannot connect; it never fails open.

## Principles for contributors

1. Treat header values, cookies and tokens as secrets in every code path.
2. Fail closed: when a check cannot be performed, reject the request.
3. No telemetry. Nothing leaves the machine except the calls to YouTube Music.
4. Provide a "delete credentials" action (`DELETE /auth`) and keep it working.

Reporting vulnerabilities: see [`../SECURITY.md`](../SECURITY.md).
