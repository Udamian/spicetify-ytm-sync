"""Entry point for the packaged executables (PyInstaller cannot run a package's __main__)."""

from ytm_sync_companion.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
