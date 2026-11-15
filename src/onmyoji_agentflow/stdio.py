"""Keep machine-readable stdout clean of text printed by native libraries.

MuMu's external_renderer_ipc.dll prints lines such as ``nemu_connect instance_name: ...`` with
printf. They sit in the dll's own C runtime buffer and are only flushed when the process exits,
long after any temporary ``dup2`` around the call has been undone, so they ended up after the
JSON that ``oaf status`` / ``oaf run`` print and broke ``json.loads`` (seen on a real Win10 +
MuMu 12 machine). The fix is permanent: point file descriptor 1 at stderr for the whole
process and give Python a private duplicate of the real stdout.
"""
from __future__ import annotations

import os
import sys

_isolated = False


def isolate_stdout() -> bool:
    """Route fd 1 (what C code writes to) to stderr for the rest of the process; ``sys.stdout``
    keeps writing to the real stdout. Idempotent. Returns True when stdout is isolated.

    Does nothing when ``sys.stdout`` is not the process's fd 1 (pytest capture, embedding).
    """
    global _isolated
    if _isolated:
        return True
    try:
        if sys.stdout is None or sys.stdout.fileno() != 1:
            return False
        sys.stdout.flush()
        real = os.dup(1)
    except (AttributeError, ValueError, OSError):
        return False
    try:
        stream = os.fdopen(real, "w", encoding=sys.stdout.encoding or "utf-8",
                           errors=sys.stdout.errors or "strict", buffering=1)
    except (OSError, ValueError, LookupError):
        os.close(real)
        return False
    try:
        os.dup2(2, 1)
    except OSError:
        stream.close()
        return False
    if os.name == "nt":
        # a dll with its own (static) C runtime takes its stdout from the Win32 standard handle
        # when it is loaded, not from our fd 1: point that at stderr as well
        try:
            import ctypes
            import msvcrt
            ctypes.windll.kernel32.SetStdHandle(-11, msvcrt.get_osfhandle(2))  # STD_OUTPUT_HANDLE
        except Exception:  # noqa: BLE001
            pass
    sys.stdout = stream
    _isolated = True
    return True
