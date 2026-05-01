"""Humanness v1 runner: 3 指標を一括算出して memory/metrics/humanness/ に書き込む。

デフォルトは「直近 7 日間」を JST で計算し、各日付の JSON ファイルを更新する。
ペルソナ一貫性は週末 (土曜) 限定でフルスコア計算 (重い)。
"""
from __future__ import annotations
import argparse
import sys
from datetime import datetime, timedelta

from common import JST, METRICS_DIR
import correction_rate as cr
import proactive_response_rate as prr
import persona_consistency as pc


def today_jst() -> str:
    return datetime.now(JST).strftime("%Y-%m-%d")


def days_back(days: int, end: str) -> str:
    end_d = datetime.strptime(end, "%Y-%m-%d")
    return (end_d - timedelta(days=days)).strftime("%Y-%m-%d")


def run(start: str, end: str, persona: bool, persona_n: int, model: str) -> None:
    print(f"[runner] window {start} → {end}", file=sys.stderr)

    print("[runner] correction_rate…", file=sys.stderr)
    msgs = list(cr.iter_conversations(start, end))
    corr = cr.detect_corrections(msgs)
    for d, v in corr.items():
        cr.write_metric(d, "correction", v)
    print(f"  wrote {len(corr)} day(s)", file=sys.stderr)

    print("[runner] proactive_response_rate…", file=sys.stderr)
    rows = prr.load_history()
    pdaily = prr.aggregate(rows, start, end)
    for d, v in pdaily.items():
        prr.write_metric(d, "proactive_response", v)
    print(f"  wrote {len(pdaily)} day(s)", file=sys.stderr)

    if persona:
        print(f"[runner] persona_consistency (n={persona_n})…", file=sys.stderr)
        samples = pc.sample_utterances(start, end, persona_n, seed=42)
        cache = pc.load_cache()
        judged = {}
        for p, items in samples.items():
            if p not in pc.PERSONA_DESCRIPTIONS:
                continue
            print(f"  [{p}] {len(items)} samples", file=sys.stderr)
            out = []
            for idx, it in enumerate(items, 1):
                it["judgment"] = pc.judge(p, it["text"], model, cache)
                out.append(it)
                if idx % 10 == 0:
                    pc.save_cache(cache)
                    print(f"    {idx}/{len(items)}", file=sys.stderr)
            judged[p] = out
            pc.save_cache(cache)
        result = pc.aggregate(judged, (start, end))
        pc.write_metric(end, "persona_consistency", result)
        print(f"  wrote persona_consistency to {end}", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start")
    ap.add_argument("--to", dest="end")
    ap.add_argument("--days", type=int, default=7, help="end から遡る日数 (default 7)")
    ap.add_argument("--persona", action="store_true", help="ペルソナ一貫性も計算 (重い)")
    ap.add_argument("--persona-n", type=int, default=30)
    ap.add_argument("--model", default=pc.DEFAULT_MODEL)
    args = ap.parse_args()

    end = args.end or today_jst()
    start = args.start or days_back(args.days - 1, end)
    run(start, end, args.persona, args.persona_n, args.model)
    print(f"\n[runner] done. metrics → {METRICS_DIR}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
