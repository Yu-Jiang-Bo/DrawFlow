"""Publish an immutable DrawFlow client payload to a central data directory."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .service.client_release import ClientReleaseStore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="发布 DrawFlow 客户端稳定版本")
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--payload", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--minimum-launcher-version", default="1.0.0")
    parser.add_argument("--notes", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    store = ClientReleaseStore(Path(args.data_dir))
    manifest = store.publish(
        Path(args.payload),
        version=args.version,
        minimum_launcher_version=args.minimum_launcher_version,
        notes=args.notes,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
