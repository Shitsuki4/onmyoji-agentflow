"""API key storage: Windows Credential Manager through ``keyring``.

Keys are only ever read at call time and never written to config, logs or
git. On non-Windows systems keyring uses the platform store (Secret Service /
Keychain); ``OAF_KEY_<NAME>`` environment variables are accepted as a fallback
for CI and testing.
"""
from __future__ import annotations

import os

SERVICE = "onmyoji-agentflow"


def _user(name: str) -> str:
    return f"llm:{name}"


def _env_name(name: str) -> str:
    return "OAF_KEY_" + "".join(c if c.isalnum() else "_" for c in name).upper()


def _keyring():
    try:
        import keyring  # type: ignore
        return keyring
    except ImportError:  # pragma: no cover
        return None


def set_key(name: str, secret: str) -> None:
    kr = _keyring()
    if kr is None:
        raise RuntimeError("没有安装 keyring，无法保存密钥")
    kr.set_password(SERVICE, _user(name), secret)


def get_key(name: str) -> str | None:
    env = os.environ.get(_env_name(name))
    if env:
        return env
    kr = _keyring()
    if kr is None:
        return None
    try:
        return kr.get_password(SERVICE, _user(name))
    except Exception:  # noqa: BLE001 - no backend available
        return None


def delete_key(name: str) -> bool:
    kr = _keyring()
    if kr is None:
        return False
    try:
        kr.delete_password(SERVICE, _user(name))
        return True
    except Exception:  # noqa: BLE001
        return False


def has_key(name: str) -> bool:
    return bool(get_key(name))
