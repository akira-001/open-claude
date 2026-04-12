#!/usr/bin/env python3
"""Audit audio fixture inventory and report common catalog issues."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


FIXTURE_ROOT = Path(__file__).resolve().parent
MANIFEST_PATH = FIXTURE_ROOT / "manifest.json"
SAMPLES_DIR = FIXTURE_ROOT / "samples"
INCOMING_DIR = FIXTURE_ROOT / "incoming"


@dataclass
class AuditReport:
    duplicate_ids: list[str]
    duplicate_files: list[str]
    missing_files: list[str]
    unregistered_samples: list[str]
    pending_incoming: list[str]

    @property
    def ok(self) -> bool:
        return not any(
            [
                self.duplicate_ids,
                self.duplicate_files,
                self.missing_files,
                self.unregistered_samples,
                self.pending_incoming,
            ]
        )


def _find_duplicates(values: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: list[str] = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    return duplicates


def audit_fixture_catalog() -> AuditReport:
    manifest = json.loads(MANIFEST_PATH.read_text())
    ids = [entry["id"] for entry in manifest]
    files = [entry["file"] for entry in manifest]

    missing_files = []
    for relative_path in files:
        path = FIXTURE_ROOT / relative_path
        if not path.exists():
            missing_files.append(relative_path)

    registered_sample_names = {Path(relative_path).name for relative_path in files}
    sample_files = sorted(path.name for path in SAMPLES_DIR.glob("*.wav"))
    incoming_files = sorted(path.name for path in INCOMING_DIR.glob("*.wav"))

    return AuditReport(
        duplicate_ids=_find_duplicates(ids),
        duplicate_files=_find_duplicates(files),
        missing_files=missing_files,
        unregistered_samples=[name for name in sample_files if name not in registered_sample_names],
        pending_incoming=incoming_files,
    )


def _print_section(title: str, values: list[str]) -> None:
    if not values:
        return
    print(f"{title}:")
    for value in values:
        print(f"  - {value}")


def main() -> None:
    report = audit_fixture_catalog()
    if report.ok:
        print("audio fixtures look clean")
        return

    _print_section("duplicate ids", report.duplicate_ids)
    _print_section("duplicate files", report.duplicate_files)
    _print_section("missing files", report.missing_files)
    _print_section("unregistered samples", report.unregistered_samples)
    _print_section("pending incoming", report.pending_incoming)
    raise SystemExit(1)


if __name__ == "__main__":
    main()
