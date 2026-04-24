"""LLM output evaluation framework."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from statistics import mean


@dataclass
class EvaluationCase:
    """Single prompt evaluation case."""

    prompt: str
    expected_keywords: list[str]


class LLMEvaluator:
    """Computes correctness, hallucination proxy, and latency metrics."""

    async def evaluate(self, model_fn: Callable[[str], str], cases: list[EvaluationCase]) -> dict:
        latencies: list[float] = []
        correctness_scores: list[float] = []
        hallucination_scores: list[float] = []

        for case in cases:
            start = time.perf_counter()
            output = await model_fn(case.prompt)
            latency_ms = (time.perf_counter() - start) * 1000
            latencies.append(latency_ms)

            lowered = output.lower()
            if case.expected_keywords:
                hits = sum(1 for k in case.expected_keywords if k.lower() in lowered)
                correctness = hits / len(case.expected_keywords)
            else:
                correctness = 1.0
            correctness_scores.append(correctness)

            # Proxy heuristic: very low keyword hit rate suggests likely hallucination.
            hallucination_scores.append(max(0.0, 1.0 - correctness))

        return {
            "total_cases": len(cases),
            "correctness": round(mean(correctness_scores), 4) if correctness_scores else 0.0,
            "hallucination_rate": round(mean(hallucination_scores), 4)
            if hallucination_scores
            else 0.0,
            "latency_ms_avg": round(mean(latencies), 2) if latencies else 0.0,
        }
