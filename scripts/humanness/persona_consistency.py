"""ペルソナ一貫性スコア: bot 発話が定義済みペルソナに沿っているかを Ollama judge で 0-10 採点。

ローカル LLM 限定（CLAUDE.md「外部 API 基本禁止」原則に従う）。
判定キャッシュ: tmp/persona_cache.json で重複判定を回避。
"""
from __future__ import annotations
import argparse
import hashlib
import json
import random
import re
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

from common import (
    BOT_ROLES,
    EMBER_ROOT,
    JST,
    iter_conversations,
    write_metric,
)

OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "gemma4-26b-nothink:latest"
CACHE_FILE = EMBER_ROOT / "tmp" / "persona_cache.json"

PERSONA_DESCRIPTIONS = {
    "mei": """Mei（メイ） — Akiraさんのパーソナル秘書。
- 元大手総合商社CFO、秘書検定1級
- 口調: フランクだが品位のある女性。「〜だね」「〜かな」とカジュアル、状況により「〜ですね」と丁寧
- 男性的表現（「〜だぜ」「〜だろ」）は使わない
- 思考: 慎重派（リスク先読み、データで語る、Charlie Munger 的逆算思考）
- 目的志向、先回り気配り、判断材料は的確に提供しつつ判断は委ねる""",
    "eve": """Eve（イヴ） — Akiraさんのムードメーカー兼遊び担当。元シリアルアントレプレナー（CEO）。
- 口調: 陽気でエネルギッシュ。「〜だよね！」「〜しようよ！」「ねぇねぇ」「〜でしょ！」
- 空気は読めるテンション高め、ただし うざくない
- 男性的表現（「〜だぜ」「〜だろ」）は使わない
- 思考: 楽観派（まず小さく試す、Steve Jobs 的プロダクト美学、引き算）
- 失敗から学ぶ、定性的兆候も重視""",
    "haru": """Haru（ハル） — Akiraさんの開発パートナー / 批判的思考パートナー。
- 口調: 女性らしい柔らかく親しみやすい口調（「〜だよ」「〜だね」「〜かな」）。簡潔で結論ファースト
- 事実のみ報告、曖昧さを避ける、わからないことはわからないと言う
- 思考: 仮説ファースト・反証志向。網羅探索。環境要因を先に排除
- 反論歓迎、遠慮なく指摘する
- 絵文字は使わない""",
}

PROMPT_TEMPLATE = """次の発話が指定ペルソナに沿っているかを 0〜10 で採点しなさい。
JSON のみで出力（前後に文字を付けない）。

ペルソナ定義:
{persona}

発話:
\"\"\"
{utterance}
\"\"\"

出力フォーマット:
{{"score": <0-10 の整数>, "reason": "<30字以内の根拠>"}}"""


def load_cache() -> dict:
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def save_cache(cache: dict) -> None:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2))


def cache_key(persona: str, model: str, utterance: str) -> str:
    h = hashlib.sha256(f"{persona}|{model}|{utterance}".encode()).hexdigest()
    return h[:24]


def judge(persona: str, utterance: str, model: str, cache: dict) -> dict | None:
    key = cache_key(persona, model, utterance)
    if key in cache:
        return cache[key]
    body = json.dumps({
        "model": model,
        "prompt": PROMPT_TEMPLATE.format(
            persona=PERSONA_DESCRIPTIONS[persona],
            utterance=utterance[:600],
        ),
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.0, "num_predict": 80},
    }).encode()
    req = urllib.request.Request(OLLAMA_URL, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            resp = json.loads(r.read())
    except Exception as e:
        print(f"  ollama error: {e}", file=sys.stderr)
        return None
    text = (resp.get("response") or "").strip()
    parsed = _extract_json(text)
    if parsed:
        cache[key] = parsed
    return parsed


def _extract_json(text: str) -> dict | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{[^{}]*\"score\"[^{}]*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                return None
    return None


def sample_utterances(start: str, end: str, per_persona: int, seed: int) -> dict[str, list[dict]]:
    """Collect bot utterances per persona within JST window, then random sample."""
    pools: dict[str, list[dict]] = defaultdict(list)
    for m in iter_conversations(start, end):
        if m.role not in BOT_ROLES:
            continue
        text = (m.text or "").strip()
        if len(text) < 30:  # ignore short ack
            continue
        pools[m.role].append({
            "ts": m.ts.isoformat(),
            "jst_date": m.jst_date,
            "text": text,
        })
    rng = random.Random(seed)
    picked: dict[str, list[dict]] = {}
    for persona, items in pools.items():
        rng.shuffle(items)
        picked[persona] = items[:per_persona]
    return picked


def aggregate(judged: dict[str, list[dict]], window: tuple[str, str]) -> dict:
    out = {
        "window": {"from": window[0], "to": window[1]},
        "by_persona": {},
    }
    for persona, samples in judged.items():
        scores = [s["judgment"]["score"] for s in samples if s.get("judgment") and isinstance(s["judgment"].get("score"), (int, float))]
        if not scores:
            out["by_persona"][persona] = {"n": 0, "mean": None, "median": None}
            continue
        scores.sort()
        n = len(scores)
        out["by_persona"][persona] = {
            "n": n,
            "mean": round(sum(scores) / n, 3),
            "median": scores[n // 2],
            "p25": scores[n // 4],
            "p75": scores[3 * n // 4],
            "low_examples": [
                {"score": s["judgment"]["score"], "reason": s["judgment"].get("reason"), "text": s["text"][:120]}
                for s in sorted(samples, key=lambda x: x.get("judgment", {}).get("score", 99))[:3]
                if s.get("judgment")
            ],
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", required=True)
    ap.add_argument("--to", dest="end", required=True)
    ap.add_argument("--per-persona", type=int, default=30)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    cache = load_cache()
    samples = sample_utterances(args.start, args.end, args.per_persona, args.seed)

    judged: dict[str, list[dict]] = {}
    for persona, items in samples.items():
        if persona not in PERSONA_DESCRIPTIONS:
            continue
        print(f"[{persona}] judging {len(items)} samples with {args.model}…", file=sys.stderr)
        out = []
        for idx, it in enumerate(items, 1):
            j = judge(persona, it["text"], args.model, cache)
            it["judgment"] = j
            out.append(it)
            if idx % 5 == 0:
                save_cache(cache)
                print(f"  {idx}/{len(items)}", file=sys.stderr)
        judged[persona] = out
        save_cache(cache)

    result = aggregate(judged, (args.start, args.end))
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if args.write:
        write_metric(args.end, "persona_consistency", result)
        print(f"\nwrote to {args.end} (window-end-anchored)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
