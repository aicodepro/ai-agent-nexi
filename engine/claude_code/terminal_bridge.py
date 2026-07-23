"""Optional true-PTY backend for a fully interactive embedded terminal (pywinpty).

The default UI panel streams the dispatcher's structured events (see session.py),
which is enough to watch and verify a run. This PTY backend is for the advanced
case where you want a real interactive terminal (typing into a live TUI). Needs
`pip install pywinpty` on Windows. Import-guarded so nothing breaks if it's absent.
"""
import threading


class PtySession:
    """Run a command in a pseudo-terminal, streaming raw output to a callback."""

    def __init__(self, on_output):
        self._on_output = on_output
        self._pty = None
        self._reader = None
        self.last_error = ""

    def _failed(self, operation: str, exc: Exception) -> bool:
        self.last_error = f"{operation}: {type(exc).__name__}: {exc}"
        print(f"[CLAUDE_PTY] {self.last_error}", flush=True)
        return False

    @staticmethod
    def available() -> bool:
        try:
            import winpty  # noqa: F401
            return True
        except Exception:
            return False

    def start(self, argv, cwd=None, cols=120, rows=30) -> bool:
        try:
            import winpty
            self._pty = winpty.PtyProcess.spawn(argv, cwd=cwd, dimensions=(rows, cols))
        except Exception as exc:
            return self._failed("start", exc)
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
        return True

    def _read_loop(self):
        try:
            while self._pty is not None and self._pty.isalive():
                data = self._pty.read()
                if data:
                    self._on_output(data)
        except Exception as exc:
            self._failed("read", exc)

    def write(self, data: str) -> bool:
        if self._pty is not None:
            try:
                self._pty.write(data)
                return True
            except Exception as exc:
                return self._failed("write", exc)
        return False

    def resize(self, cols: int, rows: int) -> bool:
        if self._pty is not None:
            try:
                self._pty.setwinsize(rows, cols)
                return True
            except Exception as exc:
                return self._failed("resize", exc)
        return False

    def stop(self) -> bool:
        if self._pty is not None:
            try:
                self._pty.terminate(force=True)
                return True
            except Exception as exc:
                return self._failed("stop", exc)
            finally:
                self._pty = None
        return False
