"""``ai-model-router`` command-line interface.

Commands:

- ``serve``                 run the FastAPI gateway
- ``db-init``               create/verify the SQLite schema
- ``create-key``            mint a new tenant API key
- ``list-keys``             list tenant keys (prefix + tier only)
- ``revoke-key <id>``       disable a tenant key
- ``usage``                 show persisted call/cost/cache totals
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

logger = logging.getLogger("ai_model_router")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ai-model-router")
    sub = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--db", default="", help="SQLite path (env ROUTER_DB)")
    common.add_argument("--verbose", action="store_true", help="debug logging")

    sub.add_parser("serve", parents=[common], help="run the gateway server")
    sub.add_parser("db-init", parents=[common], help="create or migrate the SQLite database")

    p_key = sub.add_parser("create-key", parents=[common], help="create a tenant API key")
    p_key.add_argument("--name", required=True, help="label for the key")
    p_key.add_argument(
        "--tier", default="free",
        choices=("free", "developer", "pro", "business"),
        help="rate-limit tier (default: free)",
    )
    p_key.add_argument("--rpm", type=int, help="requests-per-minute override")
    p_key.add_argument("--rpd", type=int, help="requests-per-day override")

    p_list = sub.add_parser("list-keys", parents=[common], help="list tenant keys")
    p_list.add_argument("--all", action="store_true", help="include revoked keys")

    p_revoke = sub.add_parser("revoke-key", parents=[common], help="revoke a tenant key")
    p_revoke.add_argument("key_id", type=int)

    sub.add_parser("usage", parents=[common], help="show persisted usage summary")
    return parser


def _log_level(verbose: bool) -> int:
    return logging.DEBUG if verbose else logging.INFO


def _storage_path(args: argparse.Namespace) -> str:
    from ai_model_router.config import Settings

    db = args.db or Settings.from_env().db_path
    if not db:
        sys.exit("storage not configured: pass --db or set ROUTER_DB")
    return str(db)


def _open_storage(db: str) -> Any:
    from ai_model_router.storage import Storage

    return Storage(db)


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from ai_model_router.config import Settings
    from ai_model_router.server import create_app

    logging.basicConfig(
        level=_log_level(args.verbose),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    settings = Settings.from_env()
    app = create_app(settings=settings)
    logger.info("starting ai-model-router on %s:%s", settings.host, settings.port)
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        access_log=False,
        log_level="info",
    )
    return 0


def cmd_db_init(args: argparse.Namespace) -> int:
    db = _storage_path(args)
    Path(db).parent.mkdir(parents=True, exist_ok=True)
    storage = _open_storage(db)
    storage.close()
    print(f"database ready at {db}")
    return 0


def cmd_create_key(args: argparse.Namespace) -> int:
    db = _storage_path(args)
    storage = _open_storage(db)
    plaintext, record = storage.create_key(
        name=args.name, tier=args.tier, rpm=args.rpm, rpd=args.rpd
    )
    storage.close()
    print(f"created key [{record.id}] {record.name} (tier={record.tier})")
    print(plaintext)
    print("store this key now; it will not be shown again")
    return 0


def cmd_list_keys(args: argparse.Namespace) -> int:
    db = _storage_path(args)
    storage = _open_storage(db)
    rows = storage.list_keys()
    storage.close()
    for row in rows:
        status = "enabled" if row.enabled else "revoked"
        if not row.enabled and not args.all:
            continue
        print(
            f"{row.id}\t{status}\t{row.tier}\t{row.prefix}...\t{row.name}"
        )
    return 0


def cmd_revoke_key(args: argparse.Namespace) -> int:
    db = _storage_path(args)
    storage = _open_storage(db)
    ok = storage.revoke_key(args.key_id)
    storage.close()
    if not ok:
        print(f"no key with id {args.key_id}", file=sys.stderr)
        return 1
    print(f"revoked key {args.key_id}")
    return 0


def cmd_usage(args: argparse.Namespace) -> int:
    db = _storage_path(args)
    storage = _open_storage(db)
    summary = storage.usage_summary()
    storage.close()
    print(f"calls:          {summary['calls']}")
    print(f"cost (USD):     {round(summary['cost'], 6)}")
    print(f"prompt tokens:  {summary['prompt_tokens']}")
    print(f"completion tok: {summary['completion_tokens']}")
    print(f"cache hits:     {summary['cached']}")
    return 0


COMMANDS = {
    "serve": cmd_serve,
    "db-init": cmd_db_init,
    "create-key": cmd_create_key,
    "list-keys": cmd_list_keys,
    "revoke-key": cmd_revoke_key,
    "usage": cmd_usage,
}


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return COMMANDS[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())