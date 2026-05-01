"""Proactive 応答率: 各 bot の proactive 発火に対する Akiraさんの反応率を JST 日次で算出。

データソース: mei-state.json / eve-state.json の history 配列
reaction 種別:
  - null         : 無反応
  - text_engaged : テキスト返信（強い肯定）
  - ok_hand 等   : スタンプ反応（弱い肯定）

precision = (text_engaged + stamped) / total
"""
from __future__ import annotations
import argparse
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from common import LEGACY_DATA_DIR, JST, parse_iso, write_metric

BOT_STATE_FILES = {
    "mei": LEGACY_DATA_DIR / "mei-state.json",
    "eve": LEGACY_DATA_DIR / "eve-state.json",
}

POSITIVE_TEXT = {"text_engaged"}
# それ以外の null でない reaction はスタンプ系として一律「弱い肯定」扱い


def load_history() -> list[dict]:
    rows: list[dict] = []
    for bot, fp in BOT_STATE_FILES.items():
        if not fp.exists():
            continue
        d = json.loads(fp.read_text())
        for h in d.get("history", []):
            sent = h.get("sentAt")
            if not sent:
                continue
            ts = parse_iso(sent)
            rows.append({
                "bot": bot,
                "ts": ts,
                "jst_date": ts.astimezone(JST).strftime("%Y-%m-%d"),
                "category": h.get("category"),
                "reaction": h.get("reaction"),
                "reactionDelta": h.get("reactionDelta", 0),
            })
    return rows


def aggregate(rows: list[dict], start: str | None, end: str | None) -> dict:
    daily: dict[str, dict] = defaultdict(lambda: {
        "sent": 0,
        "text_replied": 0,
        "stamped": 0,
        "ignored": 0,
        "by_bot": defaultdict(lambda: {"sent": 0, "text_replied": 0, "stamped": 0, "ignored": 0}),
        "by_category": defaultdict(lambda: {"sent": 0, "engaged": 0}),
    })

    for r in rows:
        d = r["jst_date"]
        if start and d < start:
            continue
        if end and d > end:
            continue
        cell = daily[d]
        cell["sent"] += 1
        cell["by_bot"][r["bot"]]["sent"] += 1
        cell["by_category"][r["category"]]["sent"] += 1

        reac = r["reaction"]
        if reac in POSITIVE_TEXT:
            cell["text_replied"] += 1
            cell["by_bot"][r["bot"]]["text_replied"] += 1
            cell["by_category"][r["category"]]["engaged"] += 1
        elif reac:
            cell["stamped"] += 1
            cell["by_bot"][r["bot"]]["stamped"] += 1
            cell["by_category"][r["category"]]["engaged"] += 1
        else:
            cell["ignored"] += 1
            cell["by_bot"][r["bot"]]["ignored"] += 1

    out = {}
    for d, c in sorted(daily.items()):
        sent = c["sent"]
        engaged = c["text_replied"] + c["stamped"]
        out[d] = {
            "sent": sent,
            "text_replied": c["text_replied"],
            "stamped": c["stamped"],
            "ignored": c["ignored"],
            "engagement_rate": round(engaged / sent, 4) if sent else 0.0,
            "text_reply_rate": round(c["text_replied"] / sent, 4) if sent else 0.0,
            "by_bot": {
                bot: {
                    **stats,
                    "engagement_rate": round(
                        (stats["text_replied"] + stats["stamped"]) / stats["sent"], 4
                    ) if stats["sent"] else 0.0,
                }
                for bot, stats in c["by_bot"].items()
            },
            "by_category": {cat: dict(stats) for cat, stats in c["by_category"].items()},
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", help="JST start date (YYYY-MM-DD)")
    ap.add_argument("--to", dest="end", help="JST end date (YYYY-MM-DD)")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    rows = load_history()
    daily = aggregate(rows, args.start, args.end)
    print(json.dumps(daily, ensure_ascii=False, indent=2))

    if args.write:
        for d, v in daily.items():
            write_metric(d, "proactive_response", v)
        print(f"\nwrote {len(daily)} day(s)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
