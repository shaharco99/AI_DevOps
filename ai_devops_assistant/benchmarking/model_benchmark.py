"""Benchmark helpers for comparing model targets."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from statistics import mean


@dataclass
class BenchmarkResult:
    """Benchmark summary for one model."""

    model: str
    avg_latency_ms: float
    avg_output_chars: float


class ModelBenchmark:
    """Runs latency and output-size benchmarks across models."""

    async def benchmark_model(
        self, model_name: str, fn: Callable[[str], Awaitable[str]], prompts: list[str]
    ) -> BenchmarkResult:
        latencies: list[float] = []
        output_sizes: list[int] = []
        for prompt in prompts:
            start = time.perf_counter()
            text = await fn(prompt)
            latencies.append((time.perf_counter() - start) * 1000)
            output_sizes.append(len(text or ""))
        return BenchmarkResult(
            model=model_name,
            avg_latency_ms=round(mean(latencies), 2) if latencies else 0.0,
            avg_output_chars=round(mean(output_sizes), 2) if output_sizes else 0.0,
        )
