#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from urllib import error, request


def _base_url() -> str:
    return os.getenv("LM_STUDIO_BASE_URL", "http://192.168.1.42:1234/v1").rstrip("/")


def _model() -> str:
    return os.getenv("LM_STUDIO_MODEL", "openai/gpt-oss-20b").strip()


def _call(url: str, payload: dict | None = None) -> None:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = request.Request(url, data=body, headers=headers, method="POST" if body is not None else "GET")
    print(f"\n=== {req.method} {url}")
    if payload is not None:
        print("payload:", json.dumps(payload, ensure_ascii=False))
    try:
        with request.urlopen(req, timeout=15) as response:
            text = response.read().decode("utf-8", errors="replace")
            print("status:", response.status)
            print(text[:4000])
    except error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        print("http_error:", exc.code)
        print(text[:4000])
    except Exception as exc:  # pragma: no cover
        print("error:", repr(exc))


def main() -> int:
    base = _base_url()
    model = _model()

    if not base.endswith("/v1"):
        print("WARNING: LM_STUDIO_BASE_URL does not end with /v1")
        print(f"Current value: {base}")
        print("Expected shape: http://<host>:1234/v1")

    _call(f"{base}/models")
    _call(
        f"{base}/chat/completions",
        {
            "model": model,
            "messages": [
                {"role": "user", "content": "Say hello in one short sentence."},
            ],
            "temperature": 0,
        },
    )
    _call(
        f"{base}/responses",
        {
            "model": model,
            "input": "Say hello in one short sentence.",
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
