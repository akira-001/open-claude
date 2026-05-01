"""Shared paths and helpers for humanness v1 metrics."""
from __future__ import annotations
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Iterator

JST = timezone(timedelta(hours=9))

LEGACY_DATA_DIR = Path(os.environ.get(
    "EMBER_LEGACY_DATA",
    "/Users/akira/workspace/claude-code-slack-bot/data",
))
CONVERSATIONS_DIR = LEGACY_DATA_DIR / "conversations"
PROACTIVE_HISTORY = LEGACY_DATA_DIR / "shared-proactive-history.json"

EMBER_ROOT = Path(__file__).resolve().parent.parent.parent
METRICS_DIR = EMBER_ROOT / "memory" / "metrics" / "humanness"

AKIRA_USER_ID = "U3SFGQXNH"
BOT_ROLES = {"mei", "eve", "haru"}


@dataclass
class Msg:
    ts: datetime          # UTC aware
    role: str
    user: str | None
    channel: str | None
    text: str
    raw: dict

    @property
    def jst_date(self) -> str:
        return self.ts.astimezone(JST).strftime("%Y-%m-%d")


def parse_iso(ts: str) -> datetime:
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    return datetime.fromisoformat(ts).astimezone(timezone.utc)


def iter_conversations(start_date: str | None = None, end_date: str | None = None) -> Iterator[Msg]:
    """Yield messages across daily JSONL files. start/end are inclusive JST date strings."""
    files = sorted(CONVERSATIONS_DIR.glob("*.jsonl"))
    for fp in files:
        date_str = fp.stem
        if start_date and date_str < start_date:
            continue
        if end_date and date_str > end_date:
            continue
        with fp.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = obj.get("timestamp")
                if not ts:
                    continue
                yield Msg(
                    ts=parse_iso(ts),
                    role=obj.get("role", ""),
                    user=obj.get("user"),
                    channel=obj.get("channel"),
                    text=obj.get("text", "") or "",
                    raw=obj,
                )


def write_metric(date: str, key: str, value: dict) -> Path:
    METRICS_DIR.mkdir(parents=True, exist_ok=True)
    out = METRICS_DIR / f"{date}.json"
    existing = {}
    if out.exists():
        try:
            existing = json.loads(out.read_text())
        except json.JSONDecodeError:
            existing = {}
    existing[key] = value
    out.write_text(json.dumps(existing, ensure_ascii=False, indent=2))
    return out
