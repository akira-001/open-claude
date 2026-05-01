#!/usr/bin/env python3
"""Register an audio fixture sample and append an entry to manifest.json."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path


FIXTURE_ROOT = Path(__file__).resolve().parent
MANIFEST_PATH = FIXTURE_ROOT / "manifest.json"
SAMPLES_DIR = FIXTURE_ROOT / "samples"
INCOMING_DIR = FIXTURE_ROOT / "incoming"


def slugify(text: str) -> str:
    normalized = text.strip().lower()
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized or "sample"


def build_names(category: str, scene: str, variant: str) -> tuple[str, str]:
    category_slug = slugify(category)
    scene_slug = slugify(scene)
    variant_slug = slugify(variant)
    fixture_id = f"{category_slug}_{scene_slug}"
    filename = f"{category_slug}__{scene_slug}__{variant_slug}.wav"
    return fixture_id, filename


def load_manifest() -> list[dict[str, str]]:
    return json.loads(MANIFEST_PATH.read_text())


def build_entry(
    *,
    category: str,
    scene: str,
    variant: str,
    transcript: str,
    expected_source: str,
    expected_intervention: str,
    notes: str,
    fixture_id_override: str | None = None,
) -> tuple[str, str, dict[str, str]]:
    fixture_id, filename = build_names(category, scene, variant)
    fixture_id = fixture_id_override or fixture_id
    entry = {
        "id": fixture_id,
        "file": f"samples/{filename}",
        "transcript": transcript,
        "expected_source": expected_source,
        "expected_intervention": expected_intervention,
        "notes": notes,
    }
    return fixture_id, filename, entry


def register_fixture_file(
    *,
    source_file: Path,
    category: str,
    scene: str,
    variant: str,
    transcript: str,
    expected_source: str,
    expected_intervention: str,
    notes: str,
    fixture_id_override: str | None = None,
    dry_run: bool = False,
) -> dict[str, str]:
    source_file = source_file.expanduser().resolve()
    if not source_file.exists():
        raise SystemExit(f"source file not found: {source_file}")
    if source_file.suffix.lower() != ".wav":
        raise SystemExit("source file must be a .wav file")

    fixture_id, filename, entry = build_entry(
        category=category,
        scene=scene,
        variant=variant,
        transcript=transcript,
        expected_source=expected_source,
        expected_intervention=expected_intervention,
        notes=notes,
        fixture_id_override=fixture_id_override,
    )
    destination = SAMPLES_DIR / filename

    manifest = load_manifest()
    if any(existing["id"] == fixture_id for existing in manifest):
        raise SystemExit(f"manifest already contains id: {fixture_id}")
    if destination.exists():
        raise SystemExit(f"destination already exists: {destination}")

    print(json.dumps(entry, ensure_ascii=False, indent=2))
    if dry_run:
        return entry

    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_file, destination)
    manifest.append(entry)
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(f"registered fixture: {destination}")
    return entry


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_file", help="Path to the recorded WAV file")
    parser.add_argument("--category", required=True, help="Fixture category, e.g. keyboard / monologue / question")
    parser.add_argument("--scene", required=True, help="Short scene name, e.g. schedule_planning")
    parser.add_argument("--variant", default="01", help="Variant label, default: 01")
    parser.add_argument("--id", dest="fixture_id_override", help="Optional explicit manifest id override")
    parser.add_argument("--transcript", required=True, help="Observed Whisper transcript for this sample")
    parser.add_argument("--expected-source", required=True, help="Expected source classification")
    parser.add_argument("--expected-intervention", required=True, choices=["skip", "backchannel", "reply"], help="Expected intervention")
    parser.add_argument("--notes", required=True, help="One-line note about the scenario")
    parser.add_argument("--dry-run", action="store_true", help="Print the manifest entry without writing files")
    args = parser.parse_args()

    register_fixture_file(
        source_file=Path(args.source_file),
        category=args.category,
        scene=args.scene,
        variant=args.variant,
        transcript=args.transcript,
        expected_source=args.expected_source,
        expected_intervention=args.expected_intervention,
        notes=args.notes,
        fixture_id_override=args.fixture_id_override,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
