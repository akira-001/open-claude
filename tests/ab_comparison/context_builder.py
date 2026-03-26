"""Build context for A/B comparison agents.

Agent A (without cogmem): Gets only the question and basic project description.
Agent B (with cogmem): Gets the question + cogmem search results + error patterns + knowledge summary.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
KNOWLEDGE_DIR = PROJECT_ROOT / "memory" / "knowledge"


def build_without_cogmem(question: str) -> str:
    """Build context for Agent A — no memory, just project basics."""
    return f"""You are Haru, an AI development partner working on the cogmem-agent project.
You have NO memory of past sessions. Answer based only on what you can infer from the question.

Question: {question}

Answer concisely in Japanese."""


def build_with_cogmem(question: str, cogmem_query: str) -> str:
    """Build context for Agent B — with cogmem search results and knowledge."""
    search_results = _run_cogmem_search(cogmem_query)
    ep_path = KNOWLEDGE_DIR / "error-patterns.md"
    error_patterns = ep_path.read_text(encoding="utf-8") if ep_path.exists() else ""
    summary_path = KNOWLEDGE_DIR / "summary.md"
    summary = summary_path.read_text(encoding="utf-8") if summary_path.exists() else ""

    return f"""You are Haru, an AI development partner working on the cogmem-agent project.
You have memory of past sessions. Use the following context to answer.

## 知識サマリー
{summary}

## エラーパターン
{error_patterns}

## 過去の記憶（cogmem search 結果）
{search_results}

---

Question: {question}

Answer concisely in Japanese. If you remember relevant past events, mention them naturally."""


def _run_cogmem_search(query: str) -> str:
    """Run cogmem search and return formatted results."""
    try:
        result = subprocess.run(
            ["cogmem", "search", query],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(PROJECT_ROOT),
        )
        return result.stdout.strip() if result.returncode == 0 else "(検索結果なし)"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return "(cogmem 実行エラー)"
