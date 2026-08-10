#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from app.datasets import register_dataset
from app.query_store import prepare_dataset_query_store


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Register a prepared COHORTome dataset release in the configured runtime."
    )
    parser.add_argument("--name", required=True)
    parser.add_argument("--root", required=True)
    parser.add_argument("--description", default="")
    parser.add_argument(
        "--visibility",
        choices=("admin_only", "restricted", "all_authenticated"),
        default="admin_only",
    )
    parser.add_argument("--allowed-user", action="append", default=[])
    parser.add_argument("--allowed-group", action="append", default=[])
    parser.add_argument(
        "--query-detail",
        choices=("summary", "detailed"),
        default="detailed",
    )
    parser.add_argument(
        "--ai-provider-access",
        choices=("blocked", "safe_summary", "detailed_allowed"),
        default="blocked",
    )
    parser.add_argument("--created-by", default="system")
    parser.add_argument("--prepare-store", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    dataset = register_dataset(
        name=args.name,
        root_path=args.root,
        description=args.description,
        visibility=args.visibility,
        allowed_users=args.allowed_user,
        allowed_groups=args.allowed_group,
        query_granularity_ceiling=args.query_detail,
        ai_provider_access=args.ai_provider_access,
        created_by=args.created_by,
    )
    status = {"status": "not_built", "ready": False}
    if args.prepare_store:
        status = prepare_dataset_query_store(str(dataset["dataset_id"]))
    print(
        json.dumps(
            {
                "dataset_id": dataset["dataset_id"],
                "visibility": dataset["visibility"],
                "query_granularity_ceiling": dataset["query_granularity_ceiling"],
                "ai_provider_access": dataset["ai_provider_access"],
                "query_store": {
                    "status": status.get("status"),
                    "ready": bool(status.get("ready")),
                },
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
