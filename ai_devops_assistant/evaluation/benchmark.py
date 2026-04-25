"""LLM evaluation test suites and benchmarking."""

import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Optional

from ai_devops_assistant.evaluation.llm_evaluator import EvaluationCase, LLMEvaluator

logger = logging.getLogger(__name__)


class EvaluationTestSuite:
    """Collection of evaluation test cases organized by category."""

    def __init__(self):
        self.test_cases: Dict[str, List[EvaluationCase]] = {}
        self._load_default_test_cases()

    def _load_default_test_cases(self):
        """Load default test cases for common DevOps and AI scenarios."""

        # DevOps Knowledge Tests
        self.test_cases["devops_knowledge"] = [
            EvaluationCase(
                prompt="What is a Kubernetes pod?",
                expected_keywords=["container", "smallest", "deployable", "unit"],
                expected_patterns=["group of one or more containers"],
                category="devops",
                difficulty="easy",
            ),
            EvaluationCase(
                prompt="Explain the difference between Docker and Kubernetes.",
                expected_keywords=["container", "orchestration", "deployment", "scaling"],
                expected_patterns=["Docker runs containers", "Kubernetes manages"],
                category="devops",
                difficulty="medium",
            ),
            EvaluationCase(
                prompt="How do you debug a failing Kubernetes deployment?",
                expected_keywords=["logs", "describe", "events", "kubectl"],
                expected_patterns=["kubectl logs", "kubectl describe"],
                category="devops",
                difficulty="medium",
            ),
        ]

        # AI/ML Knowledge Tests
        self.test_cases["ai_knowledge"] = [
            EvaluationCase(
                prompt="What is RAG in the context of LLMs?",
                expected_keywords=["retrieval", "augmented", "generation", "knowledge"],
                expected_patterns=["Retrieval-Augmented Generation"],
                category="ai",
                difficulty="medium",
            ),
            EvaluationCase(
                prompt="Explain the difference between fine-tuning and prompt engineering.",
                expected_keywords=["training", "parameters", "prompts", "adaptation"],
                expected_patterns=["fine-tuning modifies weights", "prompt engineering"],
                category="ai",
                difficulty="hard",
            ),
        ]

        # Code Generation Tests
        self.test_cases["code_generation"] = [
            EvaluationCase(
                prompt="Write a Python function to calculate factorial recursively.",
                expected_keywords=["def", "factorial", "if", "return", "n"],
                expected_patterns=["def factorial(n):", "return n * factorial(n-1)"],
                category="coding",
                difficulty="easy",
            ),
            EvaluationCase(
                prompt="Create a FastAPI endpoint that returns JSON data.",
                expected_keywords=["@app.get", "return", "json"],
                expected_patterns=["from fastapi import FastAPI", "@app.get"],
                category="coding",
                difficulty="medium",
            ),
        ]

        # Reasoning Tests
        self.test_cases["reasoning"] = [
            EvaluationCase(
                prompt="A system has 3 microservices. Service A calls B, B calls C. If C fails, what happens?",
                expected_keywords=["cascade", "failure", "error", "propagation"],
                expected_patterns=["failure propagates", "error handling"],
                category="reasoning",
                difficulty="medium",
            ),
        ]

        # Security Tests
        self.test_cases["security"] = [
            EvaluationCase(
                prompt="What are common security vulnerabilities in web applications?",
                expected_keywords=["sql injection", "xss", "csrf", "authentication"],
                expected_patterns=["SQL injection", "Cross-Site Scripting"],
                category="security",
                difficulty="medium",
            ),
        ]

    def add_test_case(self, category: str, case: EvaluationCase):
        """Add a test case to a category."""
        if category not in self.test_cases:
            self.test_cases[category] = []
        self.test_cases[category].append(case)

    def get_test_cases(self, categories: Optional[List[str]] = None) -> List[EvaluationCase]:
        """Get test cases, optionally filtered by categories."""
        if categories is None:
            # Return all test cases
            all_cases = []
            for cases in self.test_cases.values():
                all_cases.extend(cases)
            return all_cases

        # Return cases from specified categories
        filtered_cases = []
        for category in categories:
            if category in self.test_cases:
                filtered_cases.extend(self.test_cases[category])
        return filtered_cases

    def get_categories(self) -> List[str]:
        """Get list of available test categories."""
        return list(self.test_cases.keys())

    def save_to_file(self, file_path: str):
        """Save test suite to JSON file."""
        import json

        data = {}
        for category, cases in self.test_cases.items():
            data[category] = [
                {
                    "prompt": case.prompt,
                    "expected_keywords": case.expected_keywords,
                    "expected_patterns": case.expected_patterns,
                    "category": case.category,
                    "difficulty": case.difficulty,
                    "metadata": case.metadata,
                }
                for case in cases
            ]

        Path(file_path).parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2)

    def load_from_file(self, file_path: str):
        """Load test suite from JSON file."""
        import json

        with open(file_path, 'r') as f:
            data = json.load(f)

        for category, cases_data in data.items():
            self.test_cases[category] = [
                EvaluationCase(**case_data) for case_data in cases_data
            ]


class ModelBenchmarker:
    """Benchmark multiple models against test suites."""

    def __init__(self, evaluator: Optional[LLMEvaluator] = None):
        self.evaluator = evaluator or LLMEvaluator()
        self.test_suite = EvaluationTestSuite()

    async def benchmark_models(
        self,
        models: Dict[str, callable],
        categories: Optional[List[str]] = None,
        save_reports: bool = True,
        output_dir: str = "evaluation_reports",
    ) -> Dict[str, dict]:
        """Benchmark multiple models.

        Args:
            models: Dict of model_name -> async model_function
            categories: Categories to test (None for all)
            save_reports: Whether to save detailed reports
            output_dir: Directory to save reports

        Returns:
            Dict of model_name -> summary_metrics
        """
        test_cases = self.test_suite.get_test_cases(categories)
        logger.info(f"Benchmarking {len(models)} models on {len(test_cases)} test cases")

        if save_reports:
            Path(output_dir).mkdir(exist_ok=True)

        results = {}
        reports = await self.evaluator.compare_models(models, test_cases)

        for model_name, report in reports.items():
            # Save detailed report
            if save_reports:
                report_path = Path(output_dir) / f"{model_name}_evaluation.json"
                self.evaluator.save_report(report, report_path)

            # Extract summary metrics
            results[model_name] = {
                "correctness": report.correctness_avg,
                "hallucination_rate": report.hallucination_rate_avg,
                "relevance": report.relevance_avg,
                "coherence": report.coherence_avg,
                "groundedness": report.groundedness_avg,
                "latency_ms_avg": report.latency_ms_avg,
                "latency_ms_median": report.latency_ms_median,
                "total_cases": report.total_cases,
                "categories": list(report.category_breakdown.keys()),
            }

        # Generate comparison report
        if save_reports and len(models) > 1:
            self._generate_comparison_report(results, output_dir)

        return results

    def _generate_comparison_report(self, results: Dict[str, dict], output_dir: str):
        """Generate a comparison report across models."""
        import json

        comparison = {
            "benchmark_timestamp": self.evaluator._generate_report("", []).timestamp,
            "models_compared": list(results.keys()),
            "metrics": {},
            "rankings": {},
        }

        # Collect metrics across models
        metrics = ["correctness", "relevance", "coherence", "groundedness", "latency_ms_avg"]
        for metric in metrics:
            comparison["metrics"][metric] = {}
            scores = []

            for model_name, model_results in results.items():
                score = model_results.get(metric, 0)
                comparison["metrics"][metric][model_name] = score
                if metric != "latency_ms_avg":  # Lower latency is better
                    scores.append((model_name, score))
                else:
                    scores.append((model_name, -score))  # Invert for ranking

            # Rank models (higher is better for most metrics)
            ranked = sorted(scores, key=lambda x: x[1], reverse=True)
            comparison["rankings"][metric] = [model for model, _ in ranked]

        # Save comparison
        comparison_path = Path(output_dir) / "model_comparison.json"
        with open(comparison_path, 'w') as f:
            json.dump(comparison, f, indent=2)

        logger.info(f"Comparison report saved to {comparison_path}")

    async def run_quick_benchmark(
        self,
        models: Dict[str, callable],
        categories: Optional[List[str]] = None,
    ) -> str:
        """Run a quick benchmark and return formatted results."""
        results = await self.benchmark_models(models, categories, save_reports=False)

        # Format results as a readable string
        output = []
        output.append("🤖 LLM Model Benchmark Results")
        output.append("=" * 50)

        for model_name, metrics in results.items():
            output.append(f"\n📊 {model_name}")
            output.append("-" * 30)
            output.append(".4f")
            output.append(".4f")
            output.append(".4f")
            output.append(".4f")
            output.append(".4f")
            output.append(".2f")
            output.append(f"  Test Cases: {metrics['total_cases']}")

        # Simple ranking
        if len(results) > 1:
            output.append("🏆 Overall Ranking (by correctness)")
            ranking = sorted(results.items(), key=lambda x: x[1]['correctness'], reverse=True)
            for i, (model, _) in enumerate(ranking, 1):
                output.append(f"  {i}. {model}")

        return "\n".join(output)


# Convenience functions
async def quick_evaluate_model(
    model_fn: callable,
    model_name: str,
    categories: Optional[List[str]] = None,
) -> dict:
    """Quick evaluation of a single model."""
    benchmarker = ModelBenchmarker()
    results = await benchmarker.benchmark_models(
        {model_name: model_fn},
        categories=categories,
        save_reports=False,
    )
    return results[model_name]
