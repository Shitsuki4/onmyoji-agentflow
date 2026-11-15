"""Device layer: MuMu 12 discovery, adb and nemu_ipc backends, humanized control."""
from __future__ import annotations

import sys

from ..log import logger
from .adb import AdbDevice, find_adb
from .base import Controller, Device
from .humanize import HumanizeConfig
from .mumu import MuMuInstance, default_serial, discover, find_mumu_roots, serial_to_id

__all__ = ["AdbDevice", "Controller", "Device", "HumanizeConfig", "MuMuInstance", "open_device",
           "discover", "default_serial", "find_mumu_roots", "serial_to_id"]


def open_device(instance_cfg: dict, mumu_root: str | None = None, adb_path: str | None = None) -> Device:
    """Open a device for one configured instance.

    instance_cfg keys: ``serial`` (or ``mumu_id``), ``method``: ``auto`` | ``nemu_ipc`` | ``adb``.
    ``auto`` follows OAS's recommendation for MuMu 12: nemu_ipc when available, else adb.
    """
    serial = instance_cfg.get("serial")
    mumu_id = instance_cfg.get("mumu_id")
    if serial is None and mumu_id is not None:
        serial = default_serial(int(mumu_id))
    if serial is None:
        raise ValueError("instance needs serial or mumu_id")
    if mumu_id is None:
        mumu_id = serial_to_id(serial)
    roots = find_mumu_roots(mumu_root)
    root = roots[0] if roots else None
    adb = AdbDevice(serial, find_adb(adb_path, root))
    method = instance_cfg.get("method", "auto")
    if method in ("auto", "nemu_ipc") and sys.platform == "win32" and root and mumu_id is not None:
        try:
            from .nemu import NemuDevice
            dev = NemuDevice(root, int(mumu_id), adb=adb)
            dev.screenshot()  # probe
            logger.info("instance %s: using nemu_ipc (MuMu root %s, id %s)", serial, root, mumu_id)
            return dev
        except Exception as e:  # noqa: BLE001 - fall back like OAS
            if method == "nemu_ipc":
                raise
            logger.warning("nemu_ipc unavailable (%s), falling back to adb", e)
    logger.info("instance %s: using adb", serial)
    return adb
