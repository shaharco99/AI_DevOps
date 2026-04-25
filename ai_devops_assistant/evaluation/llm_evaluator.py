"""LLM output evaluation framework."""

import asyncio
import json
import logging
import time
from collections.abc import Callable, Awaitable
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean, median, stdev
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)


@dataclass
class EvaluationCase:
    """Single prompt evaluation case."""

    prompt: str
    expected_keywords: List[str] = field(default_factory=list)
    expected_patterns: List[str] = field(default_factory=list)
    category: str = "general"
    difficulty: str = "medium"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EvaluationResult:
    """Result of evaluating a single case."""

    case: EvaluationCase
    output: str
    latency_ms: float
    correctness_score: float
    hallucination_score: float
    relevance_score: float
    coherence_score: float
    groundedness_score: float
    metrics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelEvaluationReport:
    """Comprehensive evaluation report for a model."""

    model_name: str
    total_cases: int
    correctness_avg: float
    hallucination_rate_avg: float
    relevance_avg: float
    coherence_avg: float
    groundedness_avg: float
    latency_ms_avg: float
    latency_ms_median: float
    latency_ms_stdev: float
    results: List[EvaluationResult]
    category_breakdown: Dict[str, Dict[str, float]]
    timestamp: str


class LLMEvaluator:
    """Comprehensive LLM evaluation framework with multiple metrics."""

    def __init__(
        self,
        metrics: Optional[List[str]] = None,
        use_rag_context: bool = False,
        custom_evaluators: Optional[Dict[str, Callable]] = None,
    ):
        """Initialize evaluator.

        Args:
            metrics: List of metrics to compute
            use_rag_context: Whether to use RAG for context evaluation
            custom_evaluators: Custom evaluation functions
        """
        self.metrics = metrics or [
            "correctness", "hallucination", "relevance",
            "coherence", "groundedness", "latency"
        ]
        self.use_rag_context = use_rag_context
        self.custom_evaluators = custom_evaluators or {}

        # Initialize RAG if needed
        self.rag_pipeline = None
        if self.use_rag_context:
            try:
                from ai_devops_assistant.rag.pipeline import RAGPipeline
                self.rag_pipeline = RAGPipeline()
            except ImportError:
                logger.warning("RAG pipeline not available for context evaluation")

    async def evaluate_model(
        self,
        model_fn: Callable[[str], Awaitable[str]],
        model_name: str,
        cases: List[EvaluationCase],
        batch_size: int = 5,
    ) -> ModelEvaluationReport:
        """Evaluate a model on a set of test cases.

        Args:
            model_fn: Async function that takes a prompt and returns response
            model_name: Name of the model being evaluated
            cases: List of evaluation cases
            batch_size: Number of concurrent evaluations

        Returns:
            Comprehensive evaluation report
        """
        logger.info(f"Starting evaluation of {model_name} on {len(cases)} cases")

        # Evaluate in batches to control concurrency
        results = []
        for i in range(0, len(cases), batch_size):
            batch_cases = cases[i:i + batch_size]
            batch_results = await asyncio.gather(*[
                self._evaluate_single_case(model_fn, case)
                for case in batch_cases
            ])
            results.extend(batch_results)

        # Generate report
        report = self._generate_report(model_name, results)
        logger.info(f"Evaluation complete for {model_name}")
        return report

    async def _evaluate_single_case(
        self,
        model_fn: Callable[[str], Awaitable[str]],
        case: EvaluationCase
    ) -> EvaluationResult:
        """Evaluate a single test case."""
        start_time = time.perf_counter()

        try:
            # Get model response
            output = await model_fn(case.prompt)
        except Exception as e:
            logger.error(f"Model call failed for case: {case.prompt[:50]}... Error: {e}")
            output = f"ERROR: {str(e)}"

        latency_ms = (time.perf_counter() - start_time) * 1000

        # Compute metrics
        metrics = await self._compute_metrics(case, output)

        return EvaluationResult(
            case=case,
            output=output,
            latency_ms=latency_ms,
            correctness_score=metrics.get("correctness", 0.0),
            hallucination_score=metrics.get("hallucination", 0.0),
            relevance_score=metrics.get("relevance", 0.0),
            coherence_score=metrics.get("coherence", 0.0),
            groundedness_score=metrics.get("groundedness", 0.0),
            metrics=metrics,
        )

    async def _compute_metrics(self, case: EvaluationCase, output: str) -> Dict[str, float]:
        """Compute all evaluation metrics."""
        metrics = {}

        if "correctness" in self.metrics:
            metrics["correctness"] = self._compute_correctness(case, output)

        if "hallucination" in self.metrics:
            metrics["hallucination"] = self._compute_hallucination(case, output)

        if "relevance" in self.metrics:
            metrics["relevance"] = self._compute_relevance(case, output)

        if "coherence" in self.metrics:
            metrics["coherence"] = self._compute_coherence(output)

        if "groundedness" in self.metrics:
            metrics["groundedness"] = await self._compute_groundedness(case, output)

        # Custom evaluators
        for name, evaluator_fn in self.custom_evaluators.items():
            try:
                metrics[name] = evaluator_fn(case, output)
            except Exception as e:
                logger.error(f"Custom evaluator {name} failed: {e}")
                metrics[name] = 0.0

        return metrics

    def _compute_correctness(self, case: EvaluationCase, output: str) -> float:
        """Compute correctness based on expected keywords and patterns."""
        if not case.expected_keywords and not case.expected_patterns:
            return 1.0  # No expectations = assume correct

        lowered_output = output.lower()
        score = 0.0
        total_checks = 0

        # Check keywords
        for keyword in case.expected_keywords:
            total_checks += 1
            if keyword.lower() in lowered_output:
                score += 1.0

        # Check patterns (simple substring matching)
        for pattern in case.expected_patterns:
            total_checks += 1
            if pattern.lower() in lowered_output:
                score += 1.0

        return score / total_checks if total_checks > 0 else 0.0

    def _compute_hallucination(self, case: EvaluationCase, output: str) -> float:
        """Compute hallucination score (proxy based on factual consistency)."""
        # Simple proxy: if correctness is low, assume higher hallucination
        correctness = self._compute_correctness(case, output)

        # Additional checks for hallucination indicators
        hallucination_indicators = [
            "i'm not sure", "i don't know", "let me think",
            "as far as i know", "i believe", "i think"
        ]

        lowered_output = output.lower()
        uncertainty_score = sum(1 for indicator in hallucination_indicators
                              if indicator in lowered_output) / len(hallucination_indicators)

        # Combine correctness and uncertainty
        return min(1.0, (1.0 - correctness) + uncertainty_score * 0.3)

    def _compute_relevance(self, case: EvaluationCase, output: str) -> float:
        """Compute relevance score based on semantic similarity."""
        # Simple relevance based on keyword overlap with prompt
        prompt_words = set(case.prompt.lower().split())
        output_words = set(output.lower().split())

        if not prompt_words:
            return 0.0

        overlap = len(prompt_words.intersection(output_words))
        return overlap / len(prompt_words)

    def _compute_coherence(self, output: str) -> float:
        """Compute coherence score based on text structure."""
        if len(output.strip()) < 10:
            return 0.0

        # Simple coherence heuristics
        score = 0.0

        # Check for complete sentences
        sentences = [s.strip() for s in output.split('.') if s.strip()]
        if sentences:
            complete_sentences = sum(1 for s in sentences if len(s) > 5)
            score += (complete_sentences / len(sentences)) * 0.4

        # Check for reasonable length
        word_count = len(output.split())
        if 10 <= word_count <= 500:
            score += 0.3
        elif word_count > 500:
            score += 0.2  # Penalize overly long responses

        # Check for punctuation variety
        punctuation = sum(1 for char in output if char in '.,!?;:')
        if punctuation > 0:
            score += 0.3

        return min(1.0, score)

    async def _compute_groundedness(self, case: EvaluationCase, output: str) -> float:
        """Compute groundedness score using RAG context."""
        if not self.rag_pipeline or not self.use_rag_context:
            return 0.5  # Neutral score if no RAG available

        try:
            # Query RAG for relevant context
            rag_result = await self.rag_pipeline.query(case.prompt, top_k=3)

            if not rag_result.documents:
                return 0.3  # Low groundedness if no relevant context

            # Check if output content appears in retrieved documents
            output_lower = output.lower()
            grounded_score = 0.0

            for doc in rag_result.documents:
                doc_content = doc.content.lower()
                # Simple overlap scoring
                words_in_common = set(output_lower.split()) & set(doc_content.split())
                if words_in_common:
                    overlap_ratio = len(words_in_common) / len(set(output_lower.split()))
                    grounded_score = max(grounded_score, overlap_ratio)

            return min(1.0, grounded_score + 0.2)  # Boost for having context available

        except Exception as e:
            logger.error(f"Groundedness computation failed: {e}")
            return 0.5

    def _generate_report(self, model_name: str, results: List[EvaluationResult]) -> ModelEvaluationReport:
        """Generate comprehensive evaluation report."""
        if not results:
            return ModelEvaluationReport(
                model_name=model_name,
                total_cases=0,
                correctness_avg=0.0,
                hallucination_rate_avg=0.0,
                relevance_avg=0.0,
                coherence_avg=0.0,
                groundedness_avg=0.0,
                latency_ms_avg=0.0,
                latency_ms_median=0.0,
                latency_ms_stdev=0.0,
                results=[],
                category_breakdown={},
                timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
            )

        # Aggregate metrics
        correctness_scores = [r.correctness_score for r in results]
        hallucination_scores = [r.hallucination_score for r in results]
        relevance_scores = [r.relevance_score for r in results]
        coherence_scores = [r.coherence_score for r in results]
        groundedness_scores = [r.groundedness_score for r in results]
        latencies = [r.latency_ms for r in results]

        # Category breakdown
        category_breakdown = {}
        categories = set(r.case.category for r in results)
        for category in categories:
            category_results = [r for r in results if r.case.category == category]
            if category_results:
                category_breakdown[category] = {
                    "correctness": mean(r.correctness_score for r in category_results),
                    "hallucination": mean(r.hallucination_score for r in category_results),
                    "relevance": mean(r.relevance_score for r in category_results),
                    "coherence": mean(r.coherence_score for r in category_results),
                    "groundedness": mean(r.groundedness_score for r in category_results),
                    "latency_ms": mean(r.latency_ms for r in category_results),
                    "count": len(category_results),
                }

        return ModelEvaluationReport(
            model_name=model_name,
            total_cases=len(results),
            correctness_avg=round(mean(correctness_scores), 4),
            hallucination_rate_avg=round(mean(hallucination_scores), 4),
            relevance_avg=round(mean(relevance_scores), 4),
            coherence_avg=round(mean(coherence_scores), 4),
            groundedness_avg=round(mean(groundedness_scores), 4),
            latency_ms_avg=round(mean(latencies), 2),
            latency_ms_median=round(median(latencies), 2),
            latency_ms_stdev=round(stdev(latencies), 2) if len(latencies) > 1 else 0.0,
            results=results,
            category_breakdown=category_breakdown,
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
        )

    async def compare_models(
        self,
        models: Dict[str, Callable[[str], Awaitable[str]]],
        cases: List[EvaluationCase],
    ) -> Dict[str, ModelEvaluationReport]:
        """Compare multiple models on the same test cases."""
        logger.info(f"Comparing {len(models)} models on {len(cases)} cases")

        reports = {}
        for model_name, model_fn in models.items():
            report = await self.evaluate_model(model_fn, model_name, cases)
            reports[model_name] = report

        return reports

    def save_report(self, report: ModelEvaluationReport, file_path: Union[str, Path]) -> None:
        """Save evaluation report to JSON file."""
        path = Path(file_path)

        # Convert dataclasses to dicts for JSON serialization
        report_dict = {
            "model_name": report.model_name,
            "total_cases": report.total_cases,
            "correctness_avg": report.correctness_avg,
            "hallucination_rate_avg": report.hallucination_rate_avg,
            "relevance_avg": report.relevance_avg,
            "coherence_avg": report.coherence_avg,
            "groundedness_avg": report.groundedness_avg,
            "latency_ms_avg": report.latency_ms_avg,
            "latency_ms_median": report.latency_ms_median,
            "latency_ms_stdev": report.latency_ms_stdev,
            "category_breakdown": report.category_breakdown,
            "timestamp": report.timestamp,
            "results": [
                {
                    "case": {
                        "prompt": r.case.prompt,
                        "expected_keywords": r.case.expected_keywords,
                        "expected_patterns": r.case.expected_patterns,
                        "category": r.case.category,
                        "difficulty": r.case.difficulty,
                        "metadata": r.case.metadata,
                    },
                    "output": r.output,
                    "latency_ms": r.latency_ms,
                    "correctness_score": r.correctness_score,
                    "hallucination_score": r.hallucination_score,
                    "relevance_score": r.relevance_score,
                    "coherence_score": r.coherence_score,
                    "groundedness_score": r.groundedness_score,
                    "metrics": r.metrics,
                }
                for r in report.results
            ]
        }

        with open(path, 'w') as f:
            json.dump(report_dict, f, indent=2)

        logger.info(f"Report saved to {path}")

    def load_report(self, file_path: Union[str, Path]) -> ModelEvaluationReport:
        """Load evaluation report from JSON file."""
        path = Path(file_path)

        with open(path, 'r') as f:
            data = json.load(f)

        # Reconstruct dataclasses
        results = []
        for r in data["results"]:
            case = EvaluationCase(**r["case"])
            result = EvaluationResult(
                case=case,
                output=r["output"],
                latency_ms=r["latency_ms"],
                correctness_score=r["correctness_score"],
                hallucination_score=r["hallucination_score"],
                relevance_score=r["relevance_score"],
                coherence_score=r["coherence_score"],
                groundedness_score=r["groundedness_score"],
                metrics=r["metrics"],
            )
            results.append(result)

        return ModelEvaluationReport(
            model_name=data["model_name"],
            total_cases=data["total_cases"],
            correctness_avg=data["correctness_avg"],
            hallucination_rate_avg=data["hallucination_rate_avg"],
            relevance_avg=data["relevance_avg"],
            coherence_avg=data["coherence_avg"],
            groundedness_avg=data["groundedness_avg"],
            latency_ms_avg=data["latency_ms_avg"],
            latency_ms_median=data["latency_ms_median"],
            latency_ms_stdev=data["latency_ms_stdev"],
            results=results,
            category_breakdown=data["category_breakdown"],
            timestamp=data["timestamp"],
        )


# Backward compatibility
async def evaluate(model_fn: Callable[[str], str], cases: List[EvaluationCase]) -> Dict[str, Any]:
    """Backward compatibility function."""
    evaluator = LLMEvaluator()
    report = await evaluator.evaluate_model(model_fn, "model", cases)
    return {
        "total_cases": report.total_cases,
        "correctness": report.correctness_avg,
        "hallucination_rate": report.hallucination_rate_avg,
        "latency_ms_avg": report.latency_ms_avg,
    }
