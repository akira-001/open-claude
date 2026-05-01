"""訂正シグナル: bot 発話直後の Akiraさん再指示／訂正を JST 日次で算出する。

実データ調査の結果、Akiraさんは明示的な訂正マーカー（「違う」等）をほぼ使わず、
短い再指示で軌道修正する。よって以下の二系統を出力する。

1. explicit: 「違う」「そうじゃない」等の明示マーカー（強い証拠／少ない）
2. redirect: bot 直後 60s 以内、30 字未満の Akira 発話で ack 系（OK/ありがとう/詳細教えて）でないもの
"""
from __future__ import annotations
import argparse
import json
import re
from collections import defaultdict
from datetime import timedelta
from typing import Iterable

from common import (
    AKIRA_USER_ID,
    BOT_ROLES,
    JST,
    Msg,
    iter_conversations,
    write_metric,
)

# 訂正マーカー（bot 応答を否定する強い手掛かりのみ。新規指示と区別）
# 注: 「修正して」「直して」は新規指示の可能性が高いため除外。
STRONG_PATTERNS = [
    r"違うよ", r"違うって", r"違うね", r"ちがうよ", r"ちがうって",
    r"そうじゃない", r"そうじゃなくて", r"そうではなく",
    r"^じゃなくて", r"じゃなくてさ", r"じゃなくて、",
    r"そうじゃなく",
    r"^やめて", r"^やめろ", r"^stop$",
    r"^違う", r"^ちがう", r"^違います", r"^no$",
    r"そうじゃないって", r"勘違いして",
    r"訂正(する|して|します)",
    r"間違って(る|いる)よ", r"間違ってない",
    r"そういうことじゃなく",
]
PATTERN = re.compile("|".join(STRONG_PATTERNS), re.IGNORECASE | re.MULTILINE)

# ack / 純粋な追加質問（訂正ではない）
ACK_PATTERNS = [
    r"^OK\b", r"^ok\b", r"^おk", r"^了解",
    r"^[Yy]es\b", r"^はい", r"^うん", r"^うんうん",
    r"^ありがとう", r"^あり[がか]と", r"^サンクス",
    r"^詳細教えて", r"^詳しく教えて", r"^詳しく", r"^もっと教えて",
    r"^もう少し詳しく", r"^詳細", r"^続けて", r"^つづけて",
    r"^おはよ", r"^おやすみ", r"^お疲れ",
    r"^テスト", r"^test\b", r"^A$", r"^[0-9]$",
    r"^[!-?]+$",  # 単独記号のみ
]
ACK_RE = re.compile("|".join(ACK_PATTERNS), re.IGNORECASE)

# 末尾が ？/? の純粋な追加質問は redirect ではなく follow-up とみなす
QUESTION_RE = re.compile(r"[?？]\s*$")

REPLY_WINDOW = timedelta(minutes=10)
REDIRECT_WINDOW = timedelta(seconds=60)
REDIRECT_MAX_CHARS = 30


def detect_corrections(msgs: Iterable[Msg]) -> dict:
    """Walk messages chronologically per channel; pair bot → Akira reply within window."""
    by_channel: dict[str, list[Msg]] = defaultdict(list)
    for m in msgs:
        if m.channel:
            by_channel[m.channel].append(m)

    daily: dict[str, dict] = defaultdict(lambda: {
        "pairs": 0,
        "explicit": 0,
        "redirect": 0,
        "explicit_examples": [],
        "redirect_examples": [],
    })

    for ch, ms in by_channel.items():
        ms.sort(key=lambda x: x.ts)
        last_bot: Msg | None = None
        for m in ms:
            if m.role in BOT_ROLES:
                last_bot = m
                continue
            if m.role != "user" or m.user != AKIRA_USER_ID:
                continue
            if last_bot is None:
                continue
            gap = m.ts - last_bot.ts
            if gap > REPLY_WINDOW:
                last_bot = None
                continue
            date = m.jst_date
            daily[date]["pairs"] += 1
            text = m.text.strip()

            is_explicit = bool(PATTERN.search(text))
            is_redirect = (
                gap <= REDIRECT_WINDOW
                and len(text) <= REDIRECT_MAX_CHARS
                and len(text) > 0
                and not ACK_RE.search(text)
                and not QUESTION_RE.search(text)
                and not is_explicit
            )

            if is_explicit:
                daily[date]["explicit"] += 1
                if len(daily[date]["explicit_examples"]) < 3:
                    daily[date]["explicit_examples"].append({
                        "ts": m.ts.astimezone(JST).isoformat(),
                        "bot": last_bot.role,
                        "bot_text": last_bot.text[:120],
                        "akira_text": text[:200],
                    })
            if is_redirect:
                daily[date]["redirect"] += 1
                if len(daily[date]["redirect_examples"]) < 3:
                    daily[date]["redirect_examples"].append({
                        "ts": m.ts.astimezone(JST).isoformat(),
                        "gap_s": int(gap.total_seconds()),
                        "bot": last_bot.role,
                        "bot_text": last_bot.text[:80],
                        "akira_text": text,
                    })
            last_bot = None

    out = {}
    for date, d in sorted(daily.items()):
        pairs = d["pairs"]
        out[date] = {
            "pairs": pairs,
            "explicit_count": d["explicit"],
            "explicit_rate": round(d["explicit"] / pairs, 4) if pairs else 0.0,
            "redirect_count": d["redirect"],
            "redirect_rate": round(d["redirect"] / pairs, 4) if pairs else 0.0,
            "friction_rate": round((d["explicit"] + d["redirect"]) / pairs, 4) if pairs else 0.0,
            "explicit_examples": d["explicit_examples"],
            "redirect_examples": d["redirect_examples"],
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", help="JST start date (YYYY-MM-DD)")
    ap.add_argument("--to", dest="end", help="JST end date (YYYY-MM-DD)")
    ap.add_argument("--write", action="store_true", help="write to memory/metrics/humanness/")
    args = ap.parse_args()

    msgs = list(iter_conversations(args.start, args.end))
    daily = detect_corrections(msgs)

    print(json.dumps(daily, ensure_ascii=False, indent=2))

    if args.write:
        for date, value in daily.items():
            write_metric(date, "correction", value)
        print(f"\nwrote {len(daily)} day(s) to memory/metrics/humanness/", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
