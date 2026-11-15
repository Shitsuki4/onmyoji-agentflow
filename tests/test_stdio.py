"""Native text written to fd 1 (MuMu's ipc dll printf, flushed at process exit) must not end up
in machine-readable stdout."""
import json
import os
import subprocess
import sys

SCRIPT = r"""
import os, sys, json
from onmyoji_agentflow.stdio import isolate_stdout
assert isolate_stdout() and isolate_stdout()
os.write(1, b"nemu_connect instance_name: x\n")   # what C code writes to fd 1
print(json.dumps({"ok": True}))
sys.stdout.buffer.write(b'{"jsonrpc": "2.0"}\n')  # what the MCP stdio server writes
"""


def test_isolate_stdout_subprocess():
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([os.path.join(os.path.dirname(__file__), "..", "src"),
                                                        os.environ.get("PYTHONPATH", "")])}
    p = subprocess.run([sys.executable, "-c", SCRIPT], capture_output=True, env=env, timeout=60)
    assert p.returncode == 0, p.stderr
    out = p.stdout.decode().splitlines()
    assert [json.loads(x) for x in out] == [{"ok": True}, {"jsonrpc": "2.0"}], out
    assert b"nemu_connect" in p.stderr


def test_isolate_stdout_skips_when_captured():
    import pytest
    from onmyoji_agentflow.stdio import isolate_stdout
    try:
        if sys.stdout.fileno() == 1:
            pytest.skip("pytest -s: stdout is the real fd 1")
    except (AttributeError, ValueError, OSError):
        pass
    # under pytest, sys.stdout is not fd 1: leave everything alone
    assert isolate_stdout() is False
