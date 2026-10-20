"""Start-with-Windows switch, controlled from the YTM Sync page.

It is only offered for the installed Windows program: the Startup shortcut must point at the
installed copy, never at a folder the person may delete (an unpacked zip, a temp folder).
Everywhere else `supported` is False and the page hides the switch.
"""

from __future__ import annotations

from pathlib import Path

from . import installer


class Autostart:
    def __init__(self, env: installer.Env | None = None) -> None:
        self.env = env or installer.Env()

    @property
    def _program(self) -> Path | None:
        return installer.program_dir(self.env)

    @property
    def supported(self) -> bool:
        program = self._program
        if not (self.env.windows and self.env.frozen and program is not None):
            return False
        try:
            return self.env.executable.parent.resolve() == program.resolve()
        except OSError:
            return False

    @property
    def _shortcut(self) -> Path:
        return installer.startup_dir(self.env) / installer.STARTUP_SHORTCUT

    def enabled(self) -> bool:
        return self.supported and self._shortcut.exists()

    def set(self, enabled: bool) -> None:
        """Create or remove the Startup shortcut. Raises `InstallError`/`OSError` on failure."""
        if not self.supported:
            raise installer.InstallError("not supported here")
        program = self._program
        if enabled and program is not None:
            exe = program / self.env.executable.name
            installer.write_startup_shortcut(self.env, exe, program)
        else:
            self._shortcut.unlink(missing_ok=True)

    def state(self) -> dict[str, bool]:
        return {"supported": self.supported, "enabled": self.enabled()}
