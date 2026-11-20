"""Inspect files and optional screenshots without creating or migrating an oaf home."""
from __future__ import annotations

import importlib.util
from pathlib import Path

from .activity import workflow_activity
from .config import Config
from .ledger import period_keys
from .marathon import load_plan
from .runtime import normalize_device_identity
from .workflow.schema import bundled_dir, load_workflow


def inspect(app=None, check_device=False, plan_path=None, home=None):
    cfg = app.cfg if app else Config(home, migrate=False)
    checks = []
    instances = cfg.get("instances") or []
    identities = [normalize_device_identity(instance) for instance in instances]
    checks.append({"name": "instances", "ok": bool(identities) and len(identities) == len(set(identities)), "detail": identities})
    ocr = importlib.util.find_spec("rapidocr_onnxruntime") is not None
    checks.append({"name": "ocr", "ok": ocr, "detail": "已安装" if ocr else "安装 python -m pip install .[ocr]"})
    try:
        game = cfg.get("game", {})
        keys = period_keys(game.get("timezone", "Asia/Shanghai"), reset_hour=game.get("daily_reset_hour", 0))
        checks.append({"name": "reset_period", "ok": True, "periods": keys})
    except ValueError as error:
        checks.append({"name": "reset_period", "ok": False, "error": str(error)})
    root = cfg.workspace if (cfg.workspace / "workflows").is_dir() else bundled_dir()
    workflows = {}
    for path in sorted((root / "workflows").glob("*.yaml")):
        try:
            target = load_workflow(path, [root / "resources"])
            target.validate_params()
            workflows[target.name] = target
            activity = workflow_activity(target.raw)
            samples = list((cfg.workspace / "tests" / target.name).glob("*/expect.yaml"))
            checks.append({"name": f"workflow:{target.name}", "ok": True, "digest": target.digest(),
                           "states": len(target.states), "sample_count": len(samples),
                           "coverage": "unverified" if not samples else "replay_required",
                           "battle_open": activity.battle_open() if activity else None,
                           "shop_open": activity.shop_open() if activity else None, "requires": target.requires})
        except Exception as error:
            checks.append({"name": f"workflow:{path.stem}", "ok": False, "error": str(error)})
    try:
        plan = load_plan(plan_path)
        for item in plan["items"]:
            target = workflows[item["workflow"]]
            params = dict(item.get("params") or {})
            profile = (cfg.get("game", {}).get("profiles") or {}).get(item.get("profile"), {})
            params.update(profile.get("params") or {})
            target.validate_params(params)
            activity = workflow_activity(target.raw)
            checks.append({"name": f"plan:{target.name}", "ok": True,
                "ready": (not item.get("profile") or bool(profile.get("verified") and profile.get("evidence")))
                         and (not activity or activity.battle_open()),
                "needs": "游戏任务进度需运行前扫描" if item.get("goal") else target.requires})
    except Exception as error:
        checks.append({"name": "plan", "ok": False, "error": str(error)})
    if check_device:
        from .device import open_device
        for instance in instances:
            try:
                device = app.device(instance["name"]) if app else open_device(instance, cfg.get("mumu_root"), cfg.get("adb_path"))
                frame = device.screenshot()
                height, width = frame.shape[:2]
                checks.append({"name": f"device:{instance.get('name')}", "ok": width > height and abs(width / height - 16 / 9) < .02,
                               "raw_size": [width, height]})
            except Exception as error:
                checks.append({"name": f"device:{instance.get('name')}", "ok": False, "error": str(error)})
    return {"ok": all(row["ok"] for row in checks), "home": str(cfg.home), "read_only": True, "checks": checks}
