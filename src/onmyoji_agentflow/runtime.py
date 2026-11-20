"""Cross-home device ownership backed by operating-system file locks."""
from __future__ import annotations

import hashlib
import json
import os
import threading
import tempfile
import time
from pathlib import Path

from .errors import AgentflowError


class DeviceBusy(AgentflowError):
    """The physical emulator is already owned by another oaf process."""


def normalize_device_identity(instance: dict | str | None) -> str:
    """Map common MuMu aliases to one stable physical-device key."""
    if isinstance(instance, dict):
        if instance.get("device_identity"):
            return str(instance["device_identity"])
        serial = str(instance.get("serial") or "").strip().lower()
        mumu_id = instance.get("mumu_id")
        if mumu_id is not None:
            return f"mumu:{int(mumu_id)}"
        if serial:
            return normalize_device_identity(serial)
        return "instance:" + str(instance.get("name") or "main")
    value = str(instance or "main").strip().lower()
    if value.startswith(("mumu:", "adb:", "instance:")):
        return value
    if value in {"emulator-5554", "127.0.0.1:16384", "localhost:16384", "main", "0"}:
        return "mumu:0"
    if value.startswith(("127.0.0.1:", "localhost:")):
        port = int(value.rsplit(":", 1)[-1])
        if port >= 16384 and (port - 16384) % 32 == 0:
            return f"mumu:{(port - 16384) // 32}"
        return f"adb:loopback:{port}"
    return "adb:" + value


def _lock_root() -> Path:
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        root = Path(os.environ["LOCALAPPDATA"]) / "onmyoji-agentflow" / "locks"
    else:
        root = Path(tempfile.gettempdir()) / "onmyoji-agentflow-locks"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError, TypeError):
        return {}


def _write_json(path: Path, data: dict):
    temporary = path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, default=str), encoding="utf-8")
    os.replace(temporary, path)


def _windows_process_start(pid: int):
    import ctypes

    class FileTime(ctypes.Structure):
        _fields_ = [("low", ctypes.c_uint32), ("high", ctypes.c_uint32)]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.GetProcessTimes.argtypes = [ctypes.c_void_p, ctypes.POINTER(FileTime), ctypes.POINTER(FileTime),
                                         ctypes.POINTER(FileTime), ctypes.POINTER(FileTime)]
    kernel32.GetProcessTimes.restype = ctypes.c_int
    kernel32.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
    kernel32.GetExitCodeProcess.restype = ctypes.c_int
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        return "unknown" if ctypes.get_last_error() == 5 else None
    try:
        exit_code = ctypes.c_uint32()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)) or exit_code.value != 259:
            return None
        created = FileTime()
        exited, kernel, user = FileTime(), FileTime(), FileTime()
        if not kernel32.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited),
                                        ctypes.byref(kernel), ctypes.byref(user)):
            return "unknown"
        return (created.high << 32) | created.low
    finally:
        kernel32.CloseHandle(handle)


class FileMutex:
    _guard = threading.Lock()
    _locks: dict[str, threading.RLock] = {}
    _local = threading.local()

    def __init__(self, path: Path, timeout_s: float = 0):
        self.path = Path(path).resolve()
        self.key = os.path.normcase(str(self.path))
        self.timeout_s = timeout_s
        self.file = None
        self.windows_owner = False
        self.windows_lock_dir = self.path.with_name(self.path.name + ".d")
        self.nested = False
        with self._guard:
            self.lock = self._locks.setdefault(self.key, threading.RLock())

    def __enter__(self):
        if not self.lock.acquire(timeout=max(0, self.timeout_s)):
            raise DeviceBusy(f"资源正在使用：{self.path}")
        held = getattr(self._local, "held", None)
        if held is None:
            held = self._local.held = set()
        if self.key in held:
            self.nested = True
            return self
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            deadline = time.monotonic() + max(0, self.timeout_s)
            if os.name == "nt":
                if self.path.is_dir():
                    raise IsADirectoryError(self.path)
                stale_deadline = None
                while True:
                    try:
                        self.windows_lock_dir.mkdir()
                        self.windows_owner = True
                        owner = {"pid": os.getpid(), "created": _windows_process_start(os.getpid())}
                        (self.windows_lock_dir / "owner").write_text(json.dumps(owner), encoding="ascii")
                        held.add(self.key)
                        return self
                    except FileExistsError as error:
                        try:
                            owner = json.loads((self.windows_lock_dir / "owner").read_text(encoding="ascii"))
                        except (OSError, ValueError, TypeError):
                            owner = None
                        alive = True
                        if isinstance(owner, dict):
                            current_start = _windows_process_start(int(owner["pid"]))
                            alive = (current_start == owner.get("created") or current_start == "unknown"
                                     or owner.get("created") == "unknown")
                        if owner is not None and not alive:
                            try:
                                current_owner = json.loads((self.windows_lock_dir / "owner").read_text(encoding="ascii"))
                                if current_owner == owner:
                                    (self.windows_lock_dir / "owner").unlink()
                                    self.windows_lock_dir.rmdir()
                            except (FileNotFoundError, ValueError, OSError):
                                pass
                            if not self.windows_lock_dir.exists():
                                continue
                            stale_deadline = stale_deadline or time.monotonic() + 2.0
                            if time.monotonic() < stale_deadline:
                                time.sleep(0.05)
                                continue
                        if owner is None:
                            try:
                                if time.time() - self.windows_lock_dir.stat().st_mtime > 5:
                                    self.windows_lock_dir.rmdir()
                                    continue
                            except (FileNotFoundError, OSError):
                                pass
                        if time.monotonic() >= deadline:
                            raise DeviceBusy(f"资源正被另一个进程使用：{self.path}") from error
                        time.sleep(0.05)
                    except BaseException:
                        raise
            self.file = self.path.open("a+b")
            if self.path.stat().st_size == 0:
                self.file.write(b"0")
                self.file.flush()
            while True:
                try:
                    self.file.seek(0)
                    import fcntl
                    fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    held.add(self.key)
                    return self
                except OSError as error:
                    if time.monotonic() >= deadline:
                        raise DeviceBusy(f"资源正被另一个进程使用：{self.path}") from error
                    time.sleep(0.05)
        except BaseException:
            if self.file:
                self.file.close()
            if self.windows_owner:
                try:
                    (self.windows_lock_dir / "owner").unlink()
                    self.windows_lock_dir.rmdir()
                except (FileNotFoundError, OSError):
                    pass
                self.windows_owner = False
            self.lock.release()
            raise

    def __exit__(self, *_):
        try:
            if not self.nested and self.file:
                try:
                    if os.name != "nt":
                        import fcntl
                        fcntl.flock(self.file.fileno(), fcntl.LOCK_UN)
                finally:
                    self.file.close()
                    self._local.held.discard(self.key)
            elif not self.nested and self.windows_owner:
                try:
                    (self.windows_lock_dir / "owner").unlink()
                    self.windows_lock_dir.rmdir()
                except (FileNotFoundError, OSError):
                    pass
                self.windows_owner = False
                self._local.held.discard(self.key)
        finally:
            self.lock.release()


class DeviceLease:
    """The OS releases ownership on process death; a live owner is never stolen by TTL."""

    def __init__(self, identity: str, owner: str = "oaf", ttl_s: float = 120.0):
        self.identity = normalize_device_identity(identity)
        digest = hashlib.sha256(self.identity.encode("utf-8")).hexdigest()[:20]
        self.path = _lock_root() / f"device-{digest}.json"
        self.stop_path = _lock_root() / f"device-{digest}.stop"
        self.owner = owner
        self.ttl_s = ttl_s
        self.mutex = FileMutex(self.path.with_suffix(".lock"))
        self.token = f"{os.getpid()}-{time.time_ns()}"
        self.acquired = False
        self._heartbeat_stop = threading.Event()
        self._heartbeat_thread = None
        self._info_lock = threading.RLock()

    def _read(self) -> dict | None:
        return _read_json(self.path)

    def acquire(self, blocking: bool = False, timeout_s: float = 0) -> "DeviceLease":
        self.mutex.timeout_s = timeout_s if blocking else 0
        self.mutex.__enter__()
        if self.mutex.nested:
            self.mutex.__exit__()
            raise DeviceBusy("嵌套执行必须复用现有设备租约")
        self.acquired = True
        try:
            with self._info_lock:
                _write_json(self.path, {"identity": self.identity, "owner": self.owner, "pid": os.getpid(),
                                       "token": self.token, "started": time.time(), "heartbeat": time.time(),
                                       "status": "running"})
        except BaseException:
            self.acquired = False
            self.mutex.__exit__()
            raise
        return self

    def update(self, **data):
        if self.acquired:
            with self._info_lock:
                info = self._read()
                if info.get("token") != self.token:
                    raise DeviceBusy("设备租约已发生变化")
                _write_json(self.path, {**info, **data})

    def snapshot(self):
        info = self._read()
        if info.get("status") == "running":
            try:
                with FileMutex(self.path.with_suffix(".lock")) as probe:
                    active = probe.nested
            except DeviceBusy:
                active = True
            if not active:
                info["status"] = "interrupted"
            elif time.time() - info.get("heartbeat", 0) > self.ttl_s:
                info["heartbeat_stale"] = True
        return info

    def heartbeat(self):
        self.update(heartbeat=time.time())

    def release(self):
        if not self.acquired:
            return
        self._heartbeat_stop.set()
        if self._heartbeat_thread:
            self._heartbeat_thread.join(timeout=1)
            self._heartbeat_thread = None
        try:
            self.update(status="finished", ended=time.time(), heartbeat=time.time())
        finally:
            self.acquired = False
            self.mutex.__exit__()

    def start_heartbeat(self, interval_s: float = 20.0):
        if not self.acquired or self._heartbeat_thread:
            return
        self._heartbeat_stop.clear()

        def beat():
            while not self._heartbeat_stop.wait(interval_s):
                try:
                    self.heartbeat()
                except (OSError, DeviceBusy):
                    return

        self._heartbeat_thread = threading.Thread(target=beat, name="oaf-device-heartbeat", daemon=True)
        self._heartbeat_thread.start()

    def request_stop(self, mode: str = "immediate"):
        if mode not in ("immediate", "after_battle"):
            raise ValueError("停止模式必须是 immediate 或 after_battle")
        info = self.snapshot()
        if info.get("status") == "running":
            _write_json(self.stop_path, {"token": info["token"], "mode": mode, "requested": time.time()})

    def stop_mode(self):
        info = _read_json(self.stop_path)
        return info.get("mode") if info.get("token") == self.token else None

    def stop_requested(self) -> bool:
        return self.stop_mode() == "immediate"

    def clear_stop(self):
        return None

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *_):
        self.release()


class WorkspaceLease(FileMutex):

    def __init__(self, workspace: str | Path):
        super().__init__(Path(str(Path(workspace).resolve()) + ".oaf-workspace.lock"), timeout_s=30)
