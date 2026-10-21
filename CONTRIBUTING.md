# Contributing

Thanks for helping. The project is in beta: read [`docs/architecture.md`](docs/architecture.md)
and [`docs/roadmap.md`](docs/roadmap.md) first, so you know which parts are settled and which are
still being validated (the "spikes").

## Setup

```bash
# Companion (Python 3.10+)
cd companion
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# Spicetify custom app (Node 22+)
cd ../app
npm ci
```

Run every check CI runs, from the repository root:

```bash
scripts/check.sh
```

## Ground rules

- **Secrets never leave memory or the private files.** Do not log, print or return header values,
  cookies or tokens. Error responses name *which* header is missing, never its value.
- **All `ytmusicapi` calls live in `companion/src/ytm_sync_companion/ytm.py`.** It is an
  unofficial API that can break; keeping it behind one module keeps the damage contained.
- **Tests never touch the network.** Use the fakes in `companion/tests/conftest.py`.
- **Changing the HTTP contract** between the app and the companion in an incompatible way means
  bumping `API_VERSION` in `companion/src/ytm_sync_companion/config.py` and
  `SUPPORTED_API_VERSION` in `app/src/lib/companion.ts` together.
- Keep pull requests small and describe what you tested and on which OS.
