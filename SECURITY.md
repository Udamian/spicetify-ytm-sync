# Security policy

YTM Sync handles a copy of your YouTube Music browser session (cookies and request headers).
That is sensitive: anyone holding it can act as you on that account. The threat model and the
protections are described in [`docs/security.md`](docs/security.md).

## Reporting a vulnerability

Please **do not open a public issue**. Use GitHub's private reporting instead: the
**Security** tab of this repository, then **Report a vulnerability**.

Include what you found, how to reproduce it and the version. You will get a reply as soon as
possible; this is a volunteer project, so please be patient.

## Never share your credentials

In issues, pull requests, logs and screenshots, **never paste** your cookies, `authorization`
headers, the contents of `browser.json`, or the companion's token. If you did by accident, sign
out of YouTube Music everywhere to invalidate the session and delete the post.

## Status

Beta (0.1.x). Only the latest release is supported.
