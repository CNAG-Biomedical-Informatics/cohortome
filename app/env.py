from __future__ import annotations

import os


def app_env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def app_env_has(name: str) -> bool:
    return name in os.environ
