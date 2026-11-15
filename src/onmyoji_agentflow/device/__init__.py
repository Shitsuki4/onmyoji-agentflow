"""Device layer: MuMu 12 discovery, adb and nemu_ipc backends, humanized control."""
from __future__ import annotations

import sys

from ..log import logger
from .adb import AdbDevice, find_adb
from .base import Controller, Device
from .humanize import HumanizeConfig
from .mumu import (MuMuInstance, default_serial, discover, find_ipc_dll, find_manager, find_mumu_roots,
                   serial_to_id)

__all__ = ["AdbDevice", "Controller", "Device", "HumanizeConfig", "MuMuInstance", "open_device",
           "discover", "default_serial", "find_ipc_dll", "find_manager", "find_mumu_roots", "serial_to_id"]


def open_device(instance_cfg: dict, mumu_root: str | None = None, adb_path: str | None = None) -> Device:
    """Open a device for one configured instance.

    instance_cfg keys: ``serial`` (or ``mumu_id``), ``method``: ``auto`` | ``nemu_ipc`` | ``adb``,
    ``nemu_touch``: ``auto`` | ``nemu`` | ``adb`` (which channel taps when screenshots use nemu_ipc).
    ``auto`` follows OAS's recommendation for MuMu 12: nemu_ipc when available, else adb.
    """
    serial = instance_cfg.get("serial")
    mumu_id = instance_cfg.get("mumu_id")
    if serial is None and mumu_id is not None:
        serial = default_serial(int(mumu_id))
    if serial is None:
        raise ValueError("instance needs serial or mumu_id")
    if str(serial).startswith("emulator-"):
        # MuMu lists every instance twice (127.0.0.1:16384 and emulator-5554); use the IP:port one
        if mumu_id is not None:
            logger.warning("实例序列号 %s 换成 %s（MuMu 的 emulator-XXXX 和 IP:端口 是同一个实例，只用后者）",
                           serial, default_serial(int(mumu_id)))
            serial = default_serial(int(mumu_id))
        else:
            logger.warning("实例序列号 %s 是 emulator-XXXX 形式，建议在 config.yaml 改成 127.0.0.1:16384 这类 IP:端口", serial)
    if mumu_id is None:
        mumu_id = serial_to_id(serial)
    roots = find_mumu_roots(mumu_root)
    root = roots[0] if roots else None
    adb = AdbDevice(serial, find_adb(adb_path, root))
    method = instance_cfg.get("method", "auto")
    if method in ("auto", "nemu_ipc") and sys.platform == "win32" and root and mumu_id is not None \
            and method == "auto" and find_ipc_dll(root) is None:
        logger.info("没找到 external_renderer_ipc.dll（已查 nx_main\\sdk、nx_device\\12.0\\shell\\sdk、shell\\sdk），用 adb")
        method = "adb"
    if method in ("auto", "nemu_ipc") and sys.platform == "win32" and root and mumu_id is not None:
        try:
            from .nemu import NemuDevice
            dev = NemuDevice(root, int(mumu_id), adb=adb, touch=instance_cfg.get("nemu_touch", "auto"))
            dev.screenshot()  # probe
            logger.info("instance %s: using nemu_ipc (MuMu root %s, id %s, touch via %s)", serial, root, mumu_id, dev.touch)
            return dev
        except Exception as e:  # noqa: BLE001 - fall back like OAS
            if method == "nemu_ipc":
                raise
            logger.warning("nemu_ipc unavailable (%s), falling back to adb", e)
    logger.info("instance %s: using adb", serial)
    return adb
