"""Grade agent answers against correct answers.

Scoring:
- keyword match: each grading_keyword found = +1 point
- anti-keyword penalty: each anti_keyword found = -2 points
- score = max(0, keyword_hits - anti_keyword_penalty)
- pass = score >= ceil(len(grading_keywords) / 2)  (at least half of keywords)
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class GradeResult:
    question_id: str
    passed: bool
    score: int
    max_score: int
    keywords_found: list[str]
    keywords_missed: list[str]
    anti_keywords_found: list[str]
    answer_preview: str


def grade_answer(
    question_id: str,
    answer: str,
    grading_keywords: list[str],
    grading_anti_keywords: list[str],
) -> GradeResult:
    """Grade a single answer against keywords."""
    answer_lower = answer.lower()

    keywords_found = [kw for kw in grading_keywords if kw.lower() in answer_lower]
    keywords_missed = [kw for kw in grading_keywords if kw.lower() not in answer_lower]
    anti_found = [kw for kw in grading_anti_keywords if kw.lower() in answer_lower]

    raw_score = len(keywords_found) - len(anti_found) * 2
    score = max(0, raw_score)
    max_score = len(grading_keywords)
    threshold = math.ceil(max_score / 2)
    passed = score >= threshold

    return GradeResult(
        question_id=question_id,
        passed=passed,
        score=score,
        max_score=max_score,
        keywords_found=keywords_found,
        keywords_missed=keywords_missed,
        anti_keywords_found=anti_found,
        answer_preview=answer[:200],
    )


def summarize_results(results: list[GradeResult]) -> dict:
    """Summarize grading results."""
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": f"{passed / total:.0%}" if total else "N/A",
        "details": [
            {
                "id": r.question_id,
                "passed": r.passed,
                "score": f"{r.score}/{r.max_score}",
                "missed": r.keywords_missed,
            }
            for r in results
        ],
    }
