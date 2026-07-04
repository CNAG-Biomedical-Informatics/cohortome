#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def import_file(path: Path, orthanc_url: str, authorization: str = "") -> None:
    request = Request(
        f"{orthanc_url.rstrip('/')}/instances",
        data=path.read_bytes(),
        method="POST",
        headers={"Content-Type": "application/dicom"},
    )
    if authorization:
        request.add_header("Authorization", authorization)
    with urlopen(request, timeout=20) as response:
        if not 200 <= int(response.status) < 300:
            raise RuntimeError(f"Orthanc returned HTTP {response.status} for {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Import local DICOM files into Orthanc.")
    parser.add_argument("path", type=Path, help="DICOM file or directory to import.")
    parser.add_argument("--orthanc-url", default="http://127.0.0.1:8042", help="Orthanc base URL.")
    parser.add_argument("--username", default="", help="Orthanc username, if authentication is enabled.")
    parser.add_argument("--password", default="", help="Orthanc password, if authentication is enabled.")
    args = parser.parse_args()

    if args.path.is_dir():
        files = sorted(path for path in args.path.rglob("*") if path.is_file())
    else:
        files = [args.path]
    authorization = ""
    if args.username or args.password:
        token = base64.b64encode(f"{args.username}:{args.password}".encode("utf-8")).decode("ascii")
        authorization = f"Basic {token}"
    imported = 0
    for path in files:
        try:
            import_file(path, args.orthanc_url, authorization)
        except (HTTPError, URLError, OSError) as exc:
            raise SystemExit(f"Failed to import {path}: {exc}") from exc
        imported += 1
    print(f"Imported {imported} DICOM file{'s' if imported != 1 else ''}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
