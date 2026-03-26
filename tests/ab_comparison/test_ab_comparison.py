"""A/B comparison test: cogmem vs no-cogmem agent accuracy.

Runs each question through two agents:
- Agent A: no cogmem context (just the question)
- Agent B: with cogmem context (search results + knowledge)

Uses Ollama local LLM to generate answers (zero API cost).
Grades answers against keyword-based correct answers.
Saves detailed results to tests/ab_comparison/results/.
"""

from __future__ import annotations

import json
import subprocess
import time
from datetime import datetime
from pathlib import Path

import pytest

from .context_builder import build_with_cogmem, build_without_cogmem
from .grader import grade_answer, summarize_results, GradeResult

QUESTIONS_PATH = Path(__file__).parent / "questions.json"
RESULTS_DIR = Path(__file__).parent / "results"

requires_ollama = pytest.mark.skipif(
    subprocess.run(
        ["curl", "-s", "http://localhost:11434/api/tags"],
        capture_output=True, timeout=3,
    ).returncode != 0,
    reason="Ollama not running",
)


def _ask_ollama(prompt: str, model: str = "qwen3:4b") -> str:
    """Ask Ollama a question and return the response."""
    try:
        result = subprocess.run(
            ["ollama", "run", model, prompt],
            capture_output=True,
            text=True,
            timeout=120,
        )
        return result.stdout.strip() if result.returncode == 0 else "(回答生成エラー)"
    except subprocess.TimeoutExpired:
        return "(タイムアウト)"


def _load_questions() -> list[dict]:
    """Load questions from JSON."""
    data = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
    return data["questions"]


@pytest.fixture(scope="module")
def questions():
    return _load_questions()


@pytest.fixture(scope="module")
def ab_results(questions):
    """Run all questions through both agents and collect results."""
    results_a = []  # without cogmem
    results_b = []  # with cogmem

    for q in questions:
        # Agent A: no cogmem
        prompt_a = build_without_cogmem(q["question"])
        answer_a = _ask_ollama(prompt_a)
        grade_a = grade_answer(
            q["id"], answer_a, q["grading_keywords"], q["grading_anti_keywords"]
        )
        results_a.append(grade_a)

        # Agent B: with cogmem
        prompt_b = build_with_cogmem(q["question"], q["cogmem_context_query"])
        answer_b = _ask_ollama(prompt_b)
        grade_b = grade_answer(
            q["id"], answer_b, q["grading_keywords"], q["grading_anti_keywords"]
        )
        results_b.append(grade_b)

    # Save detailed results
    RESULTS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = {
        "timestamp": timestamp,
        "model": "qwen3:4b",
        "without_cogmem": summarize_results(results_a),
        "with_cogmem": summarize_results(results_b),
    }
    result_file = RESULTS_DIR / f"ab_results_{timestamp}.json"
    result_file.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nResults saved to {result_file}")

    return results_a, results_b


@requires_ollama
class TestABComparison:
    """A/B comparison: cogmem improves agent accuracy."""

    def test_with_cogmem_beats_without_overall(self, ab_results):
        """Agent with cogmem has higher overall pass rate."""
        results_a, results_b = ab_results
        pass_a = sum(1 for r in results_a if r.passed)
        pass_b = sum(1 for r in results_b if r.passed)
        print(f"\nOverall: without={pass_a}/55, with={pass_b}/55")
        assert pass_b > pass_a, (
            f"cogmem agent ({pass_b}/55) should beat no-cogmem ({pass_a}/55)"
        )

    def test_ep_reoccurrence_with_cogmem(self, ab_results, questions):
        """Agent with cogmem passes all EP reoccurrence tests."""
        _, results_b = ab_results
        ep_ids = {q["id"] for q in questions if q["category"] == "ep_reoccurrence"}
        ep_results = [r for r in results_b if r.question_id in ep_ids]
        passed = sum(1 for r in ep_results if r.passed)
        print(f"\nEP with cogmem: {passed}/5")
        assert passed >= 4, f"EP with cogmem: {passed}/5 (need >= 4)"

    def test_ep_reoccurrence_without_cogmem_lower(self, ab_results, questions):
        """Agent without cogmem scores lower on EP tests."""
        results_a, results_b = ab_results
        ep_ids = {q["id"] for q in questions if q["category"] == "ep_reoccurrence"}
        ep_a = [r for r in results_a if r.question_id in ep_ids]
        ep_b = [r for r in results_b if r.question_id in ep_ids]
        pass_a = sum(1 for r in ep_a if r.passed)
        pass_b = sum(1 for r in ep_b if r.passed)
        print(f"\nEP: without={pass_a}/5, with={pass_b}/5")
        assert pass_b >= pass_a

    def test_context_dependent_with_cogmem(self, ab_results, questions):
        """Agent with cogmem passes most context-dependent tests."""
        _, results_b = ab_results
        ctx_ids = {q["id"] for q in questions if q["category"] == "context_dependent"}
        ctx_results = [r for r in results_b if r.question_id in ctx_ids]
        passed = sum(1 for r in ctx_results if r.passed)
        print(f"\nContext with cogmem: {passed}/50")
        assert passed >= 30, f"Context with cogmem: {passed}/50 (need >= 30)"

    def test_context_dependent_without_cogmem_lower(self, ab_results, questions):
        """Agent without cogmem scores significantly lower on context tests."""
        results_a, results_b = ab_results
        ctx_ids = {q["id"] for q in questions if q["category"] == "context_dependent"}
        ctx_a = [r for r in results_a if r.question_id in ctx_ids]
        ctx_b = [r for r in results_b if r.question_id in ctx_ids]
        pass_a = sum(1 for r in ctx_a if r.passed)
        pass_b = sum(1 for r in ctx_b if r.passed)
        print(f"\nContext: without={pass_a}/50, with={pass_b}/50")
        # cogmem should provide at least 15 more correct answers
        assert pass_b - pass_a >= 15, (
            f"cogmem advantage ({pass_b - pass_a}) should be >= 15"
        )

    def test_difficulty_correlation(self, ab_results, questions):
        """Hard questions show bigger cogmem advantage than easy ones."""
        results_a, results_b = ab_results
        q_map = {q["id"]: q for q in questions}

        def pass_rate_by_difficulty(results, difficulty):
            filtered = [r for r in results if q_map[r.question_id]["difficulty"] == difficulty]
            if not filtered:
                return 0
            return sum(1 for r in filtered if r.passed) / len(filtered)

        # Calculate advantage per difficulty
        for diff in ["easy", "medium", "hard"]:
            rate_a = pass_rate_by_difficulty(results_a, diff)
            rate_b = pass_rate_by_difficulty(results_b, diff)
            print(f"\n{diff}: without={rate_a:.0%}, with={rate_b:.0%}, advantage={rate_b-rate_a:.0%}")

        # Hard questions should show the biggest advantage
        hard_advantage = pass_rate_by_difficulty(results_b, "hard") - pass_rate_by_difficulty(results_a, "hard")
        easy_advantage = pass_rate_by_difficulty(results_b, "easy") - pass_rate_by_difficulty(results_a, "easy")
        # Not a strict assertion — just log it for observation
        print(f"\nHard advantage: {hard_advantage:.0%}, Easy advantage: {easy_advantage:.0%}")
