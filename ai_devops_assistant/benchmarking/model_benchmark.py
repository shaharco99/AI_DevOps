"""Comprehensive model benchmarking and performance analysis."""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean, median, stdev
from typing import Any, Dict, List, Optional, Union

from ai_devops_assistant.evaluation.benchmark import ModelBenchmarker

logger = logging.getLogger(__name__)


@dataclass
class BenchmarkMetrics:
    """Detailed metrics for a single benchmark run."""
    latency_ms: float
    output_tokens: Optional[int] = None
    input_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    output_length_chars: int = 0
    prompt_length_chars: int = 0
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelBenchmarkResult:
    """Comprehensive benchmark result for a model."""
    model_name: str
    total_runs: int
    successful_runs: int
    failed_runs: int
    success_rate: float

    # Latency metrics
    avg_latency_ms: float
    median_latency_ms: float
    min_latency_ms: float
    max_latency_ms: float
    avg_output_length: float
    total_output_length: int

    # Optional metrics (with defaults)
    latency_stdev: Optional[float] = None
    avg_input_tokens: Optional[float] = None
    avg_output_tokens: Optional[float] = None
    avg_total_tokens: Optional[float] = None
    tokens_per_second: Optional[float] = None
    throughput_runs_per_minute: float = 0.0

    # Individual run data
    runs: List[BenchmarkMetrics] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S"))


@dataclass
class BenchmarkComparison:
    """Comparison results across multiple models."""
    models: List[str]
    best_performer: str
    ranking: List[Dict[str, Any]]
    recommendations: List[str]
    summary_stats: Dict[str, Any]
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S"))


class AdvancedModelBenchmark:
    """Advanced benchmarking system for LLM performance analysis."""

    def __init__(
        self,
        concurrency_limit: int = 5,
        timeout_seconds: int = 60,
        include_tokenization: bool = True,
    ):
        """Initialize benchmark system.

        Args:
            concurrency_limit: Maximum concurrent benchmark runs
            timeout_seconds: Timeout for individual runs
            include_tokenization: Whether to include token counting
        """
        self.concurrency_limit = concurrency_limit
        self.timeout_seconds = timeout_seconds
        self.include_tokenization = include_tokenization
        self.semaphore = asyncio.Semaphore(concurrency_limit)

    async def benchmark_model(
        self,
        model_name: str,
        model_fn: callable,
        prompts: List[str],
        runs_per_prompt: int = 3,
    ) -> ModelBenchmarkResult:
        """Benchmark a single model across multiple prompts.

        Args:
            model_name: Name of the model being benchmarked
            model_fn: Async function that takes a prompt and returns response
            prompts: List of prompts to test
            runs_per_prompt: Number of times to run each prompt

        Returns:
            Comprehensive benchmark results
        """
        logger.info(f"Starting benchmark for {model_name} with {len(prompts)} prompts")

        all_runs = []

        # Create all benchmark tasks
        tasks = []
        for prompt in prompts:
            for run_num in range(runs_per_prompt):
                tasks.append(self._single_run(model_name, model_fn, prompt, run_num))

        # Execute with concurrency control
        semaphore = asyncio.Semaphore(self.concurrency_limit)
        async def limited_run(task):
            async with semaphore:
                return await task

        # Run all tasks
        start_time = time.time()
        results = await asyncio.gather(*[limited_run(task) for task in tasks])
        total_time = time.time() - start_time

        # Collect results
        successful_runs = []
        failed_runs = []

        for result in results:
            if result.error:
                failed_runs.append(result)
            else:
                successful_runs.append(result)
            all_runs.append(result)

        # Calculate aggregate metrics
        result = self._calculate_aggregate_metrics(model_name, successful_runs, failed_runs, total_time)

        logger.info(f"Benchmark completed for {model_name}: {result.successful_runs}/{result.total_runs} successful")
        return result

    async def _single_run(
        self,
        model_name: str,
        model_fn: callable,
        prompt: str,
        run_num: int
    ) -> BenchmarkMetrics:
        """Execute a single benchmark run."""
        try:
            start_time = time.perf_counter()

            # Execute with timeout
            response = await asyncio.wait_for(
                model_fn(prompt),
                timeout=self.timeout_seconds
            )

            latency_ms = (time.perf_counter() - start_time) * 1000

            # Extract token information if available
            input_tokens = getattr(response, 'prompt_tokens', None)
            output_tokens = getattr(response, 'completion_tokens', None)
            total_tokens = getattr(response, 'total_tokens', None)

            # Fallback tokenization if not provided
            if self.include_tokenization and not input_tokens:
                input_tokens = self._estimate_tokens(prompt)
                output_tokens = self._estimate_tokens(str(response))
                total_tokens = input_tokens + output_tokens

            return BenchmarkMetrics(
                latency_ms=round(latency_ms, 2),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                output_length_chars=len(str(response)),
                prompt_length_chars=len(prompt),
                metadata={"run_num": run_num, "model": model_name}
            )

        except asyncio.TimeoutError:
            return BenchmarkMetrics(
                latency_ms=self.timeout_seconds * 1000,
                prompt_length_chars=len(prompt),
                error=f"Timeout after {self.timeout_seconds}s",
                metadata={"run_num": run_num, "model": model_name}
            )
        except Exception as e:
            return BenchmarkMetrics(
                latency_ms=0.0,
                prompt_length_chars=len(prompt),
                error=str(e),
                metadata={"run_num": run_num, "model": model_name}
            )

    def _estimate_tokens(self, text: str) -> int:
        """Rough token estimation (4 chars ≈ 1 token)."""
        return max(1, len(text) // 4)

    def _calculate_aggregate_metrics(
        self,
        model_name: str,
        successful_runs: List[BenchmarkMetrics],
        failed_runs: List[BenchmarkMetrics],
        total_time: float
    ) -> ModelBenchmarkResult:
        """Calculate aggregate metrics from individual runs."""
        total_runs = len(successful_runs) + len(failed_runs)
        successful_count = len(successful_runs)

        if not successful_runs:
            return ModelBenchmarkResult(
                model_name=model_name,
                total_runs=total_runs,
                successful_runs=0,
                failed_runs=len(failed_runs),
                success_rate=0.0,
                avg_latency_ms=0.0,
                median_latency_ms=0.0,
                min_latency_ms=0.0,
                max_latency_ms=0.0,
                avg_output_length=0.0,
                total_output_length=0,
                runs=successful_runs + failed_runs,
            )

        # Latency calculations
        latencies = [r.latency_ms for r in successful_runs]
        avg_latency = mean(latencies)
        median_latency = median(latencies)
        min_latency = min(latencies)
        max_latency = max(latencies)
        latency_stdev = stdev(latencies) if len(latencies) > 1 else None

        # Token calculations
        input_tokens = [r.input_tokens for r in successful_runs if r.input_tokens]
        output_tokens = [r.output_tokens for r in successful_runs if r.output_tokens]
        total_tokens = [r.total_tokens for r in successful_runs if r.total_tokens]

        avg_input_tokens = mean(input_tokens) if input_tokens else None
        avg_output_tokens = mean(output_tokens) if output_tokens else None
        avg_total_tokens = mean(total_tokens) if total_tokens else None

        # Output length calculations
        output_lengths = [r.output_length_chars for r in successful_runs]
        avg_output_length = mean(output_lengths)
        total_output_length = sum(output_lengths)

        # Performance scores
        tokens_per_second = None
        if avg_total_tokens and avg_latency:
            tokens_per_second = (avg_total_tokens / avg_latency) * 1000

        throughput_runs_per_minute = (successful_count / total_time) * 60 if total_time > 0 else 0

        return ModelBenchmarkResult(
            model_name=model_name,
            total_runs=total_runs,
            successful_runs=successful_count,
            failed_runs=len(failed_runs),
            success_rate=successful_count / total_runs,
            avg_latency_ms=round(avg_latency, 2),
            median_latency_ms=round(median_latency, 2),
            min_latency_ms=round(min_latency, 2),
            max_latency_ms=round(max_latency, 2),
            latency_stdev=round(latency_stdev, 2) if latency_stdev else None,
            avg_input_tokens=round(avg_input_tokens, 2) if avg_input_tokens else None,
            avg_output_tokens=round(avg_output_tokens, 2) if avg_output_tokens else None,
            avg_total_tokens=round(avg_total_tokens, 2) if avg_total_tokens else None,
            avg_output_length=round(avg_output_length, 2),
            total_output_length=total_output_length,
            tokens_per_second=round(tokens_per_second, 2) if tokens_per_second else None,
            throughput_runs_per_minute=round(throughput_runs_per_minute, 2),
            runs=successful_runs,
        )

    async def compare_models(
        self,
        models: Dict[str, callable],
        prompts: List[str],
        runs_per_prompt: int = 3,
        output_dir: str = "benchmark_results",
    ) -> BenchmarkComparison:
        """Compare multiple models on the same benchmark suite.

        Args:
            models: Dict of model_name -> model_function
            prompts: List of prompts to test
            runs_per_prompt: Number of runs per prompt
            output_dir: Directory to save results

        Returns:
            Comparison analysis
        """
        logger.info(f"Starting comparison benchmark of {len(models)} models")

        # Run benchmarks for all models concurrently
        benchmark_tasks = [
            self.benchmark_model(name, fn, prompts, runs_per_prompt)
            for name, fn in models.items()
        ]

        results = await asyncio.gather(*benchmark_tasks)
        results_dict = {r.model_name: r for r in results}

        # Save individual results
        Path(output_dir).mkdir(exist_ok=True)
        for result in results:
            self.save_result(result, f"{output_dir}/{result.model_name}_benchmark.json")

        # Generate comparison
        comparison = self._generate_comparison(results)

        # Save comparison
        self.save_comparison(comparison, f"{output_dir}/model_comparison.json")

        logger.info(f"Comparison completed. Best performer: {comparison.best_performer}")
        return comparison

    def _generate_comparison(self, results: List[ModelBenchmarkResult]) -> BenchmarkComparison:
        """Generate comparison analysis from benchmark results."""
        if not results:
            return BenchmarkComparison(
                models=[],
                best_performer="",
                ranking=[],
                recommendations=[],
                summary_stats={}
            )

        # Rank models by multiple criteria
        ranking = []
        for result in results:
            score = (
                result.success_rate * 0.4 +  # 40% weight on reliability
                (1.0 - (result.avg_latency_ms / max(r.avg_latency_ms for r in results))) * 0.3 +  # 30% on speed (inverted)
                (result.tokens_per_second / max(r.tokens_per_second or 1 for r in results)) * 0.3  # 30% on throughput
            )

            ranking.append({
                "model": result.model_name,
                "composite_score": round(score, 3),
                "success_rate": result.success_rate,
                "avg_latency_ms": result.avg_latency_ms,
                "tokens_per_second": result.tokens_per_second,
                "throughput_rpm": result.throughput_runs_per_minute,
            })

        # Sort by composite score
        ranking.sort(key=lambda x: x["composite_score"], reverse=True)
        best_performer = ranking[0]["model"] if ranking else ""

        # Generate recommendations
        recommendations = self._generate_recommendations(ranking)

        # Summary statistics
        summary_stats = {
            "total_models": len(results),
            "avg_success_rate": mean(r.success_rate for r in results),
            "latency_range_ms": {
                "min": min(r.avg_latency_ms for r in results),
                "max": max(r.avg_latency_ms for r in results),
            },
            "best_tokens_per_second": max((r.tokens_per_second or 0) for r in results),
            "most_reliable": max(results, key=lambda r: r.success_rate).model_name,
            "fastest": min(results, key=lambda r: r.avg_latency_ms).model_name,
        }

        return BenchmarkComparison(
            models=[r.model_name for r in results],
            best_performer=best_performer,
            ranking=ranking,
            recommendations=recommendations,
            summary_stats=summary_stats,
        )

    def _generate_recommendations(self, ranking: List[Dict[str, Any]]) -> List[str]:
        """Generate recommendations based on benchmark results."""
        recommendations = []

        if not ranking:
            return ["No benchmark data available"]

        best_model = ranking[0]["model"]
        recommendations.append(f"🏆 Top performer: {best_model} (composite score: {ranking[0]['composite_score']})")

        # Check for reliability issues
        low_reliability = [r for r in ranking if r["success_rate"] < 0.8]
        if low_reliability:
            recommendations.append(f"⚠️  Low reliability detected for: {', '.join(r['model'] for r in low_reliability)}")

        # Check for performance differences
        if len(ranking) > 1:
            fastest = ranking[0]
            slowest = ranking[-1]
            speedup = slowest["avg_latency_ms"] / max(fastest["avg_latency_ms"], 1)
            if speedup > 2:
                recommendations.append(f"⚡ {fastest['model']} is {speedup:.1f}x faster than {slowest['model']}")

        # Check for high throughput
        high_throughput = [r for r in ranking if r["throughput_rpm"] > 100]
        if high_throughput:
            recommendations.append(f"🚀 High throughput models: {', '.join(r['model'] for r in high_throughput)}")

        return recommendations

    def save_result(self, result: ModelBenchmarkResult, file_path: str) -> None:
        """Save benchmark result to JSON file."""
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)

        data = {
            "model_name": result.model_name,
            "total_runs": result.total_runs,
            "successful_runs": result.successful_runs,
            "failed_runs": result.failed_runs,
            "success_rate": result.success_rate,
            "avg_latency_ms": result.avg_latency_ms,
            "median_latency_ms": result.median_latency_ms,
            "min_latency_ms": result.min_latency_ms,
            "max_latency_ms": result.max_latency_ms,
            "latency_stdev": result.latency_stdev,
            "avg_input_tokens": result.avg_input_tokens,
            "avg_output_tokens": result.avg_output_tokens,
            "avg_total_tokens": result.avg_total_tokens,
            "avg_output_length": result.avg_output_length,
            "total_output_length": result.total_output_length,
            "tokens_per_second": result.tokens_per_second,
            "throughput_runs_per_minute": result.throughput_runs_per_minute,
            "timestamp": result.timestamp,
            "runs": [
                {
                    "latency_ms": r.latency_ms,
                    "input_tokens": r.input_tokens,
                    "output_tokens": r.output_tokens,
                    "total_tokens": r.total_tokens,
                    "output_length_chars": r.output_length_chars,
                    "prompt_length_chars": r.prompt_length_chars,
                    "error": r.error,
                    "metadata": r.metadata,
                }
                for r in result.runs
            ]
        }

        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2)

    def save_comparison(self, comparison: BenchmarkComparison, file_path: str) -> None:
        """Save comparison results to JSON file."""
        Path(file_path).parent.mkdir(exist_ok=True)

        with open(file_path, 'w') as f:
            json.dump({
                "models": comparison.models,
                "best_performer": comparison.best_performer,
                "ranking": comparison.ranking,
                "recommendations": comparison.recommendations,
                "summary_stats": comparison.summary_stats,
                "timestamp": comparison.timestamp,
            }, f, indent=2)

    def load_result(self, file_path: str) -> ModelBenchmarkResult:
        """Load benchmark result from JSON file."""
        with open(file_path, 'r') as f:
            data = json.load(f)

        runs = [
            BenchmarkMetrics(**r) for r in data["runs"]
        ]

        return ModelBenchmarkResult(**{k: v for k, v in data.items() if k != "runs"}, runs=runs)

    def generate_report(
        self,
        results: List[ModelBenchmarkResult],
        output_file: str = "benchmark_report.md"
    ) -> None:
        """Generate a human-readable benchmark report."""
        report = ["# LLM Benchmark Report\n"]
        report.append(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")

        for result in results:
            report.append(f"## {result.model_name}\n")
            report.append("### Performance Metrics")
            report.append(f"- **Success Rate**: {result.success_rate:.1%}")
            report.append(f"- **Average Latency**: {result.avg_latency_ms:.0f}ms")
            report.append(f"- **Median Latency**: {result.median_latency_ms:.0f}ms")
            report.append(f"- **Throughput**: {result.throughput_runs_per_minute:.1f} runs/min")

            if result.tokens_per_second:
                report.append(f"- **Tokens/Second**: {result.tokens_per_second:.1f}")

            report.append("### Reliability")
            report.append(f"- **Successful Runs**: {result.successful_runs}/{result.total_runs}")

            if result.latency_stdev:
                report.append(f"- **Latency StdDev**: {result.latency_stdev:.0f}ms")

            report.append("")

        # Save report
        Path(output_file).parent.mkdir(exist_ok=True)
        with open(output_file, 'w') as f:
            f.write("\n".join(report))


# Backward compatibility
async def benchmark_model(
    model_name: str,
    fn: callable,
    prompts: List[str]
) -> dict:
    """Backward compatibility function."""
    benchmarker = AdvancedModelBenchmark()
    result = await benchmarker.benchmark_model(model_name, fn, prompts, runs_per_prompt=1)

    return {
        "model": result.model_name,
        "avg_latency_ms": result.avg_latency_ms,
        "avg_output_chars": result.avg_output_length,
    }
