#!/usr/bin/env python3
"""Bulk import audio fixtures from incoming/ using sidecar JSON metadata."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from .register_fixture import INCOMING_DIR, register_fixture_file
except ImportError:
    from register_fixture import INCOMING_DIR, register_fixture_file


REQUIRED_FIELDS = {
    "category",
    "scene",
    "variant",
    "transcript",
    "expected_source",
    "expected_intervention",
    "notes",
}


def load_sidecar(sidecar_path: Path) -> dict[str, str]:
    data = json.loads(sidecar_path.read_text())
    missing = sorted(REQUIRED_FIELDS - set(data))
    if missing:
        raise SystemExit(f"{sidecar_path.name} is missing required fields: {', '.join(missing)}")
    return data


def iter_sidecar_paths() -> list[Path]:
    return sorted(
        path
        for path in INCOMING_DIR.glob("*.json")
        if not path.name.endswith(".template.json")
    )


def import_incoming(*, dry_run: bool = False) -> int:
    imported = 0
    for sidecar_path in iter_sidecar_paths():
        metadata = load_sidecar(sidecar_path)
        source_file = INCOMING_DIR / f"{sidecar_path.stem}.wav"
        if not source_file.exists():
            raise SystemExit(f"matching wav not found for {sidecar_path.name}: {source_file.name}")

        print(f"importing {source_file.name}")
        register_fixture_file(
            source_file=source_file,
            category=metadata["category"],
            scene=metadata["scene"],
            variant=metadata["variant"],
            transcript=metadata["transcript"],
            expected_source=metadata["expected_source"],
            expected_intervention=metadata["expected_intervention"],
            notes=metadata["notes"],
            fixture_id_override=metadata.get("id"),
            dry_run=dry_run,
        )
        if not dry_run:
            source_file.unlink(missing_ok=True)
            sidecar_path.unlink(missing_ok=True)
        imported += 1

    if imported == 0:
        print("no incoming sidecars found")
    return imported


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Validate and print entries without writing files")
    args = parser.parse_args()
    import_incoming(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
