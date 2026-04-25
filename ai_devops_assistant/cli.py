"""CLI for model management, RAG ingestion, and evaluation."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

from ai_devops_assistant.evaluation.benchmark import ModelBenchmarker, quick_evaluate_model
from ai_devops_assistant.evaluation.llm_evaluator import EvaluationCase, LLMEvaluator
from ai_devops_assistant.rag.pipeline import SimpleRAGPipeline
from ai_devops_assistant.services.model_registry import CompositeRegistry, OllamaRegistry
from ai_devops_assistant.services.multi_llm import FallbackLLMClient


async def _search_models(query: str, limit: int) -> None:
    registry = CompositeRegistry()
    models = await registry.search_models(query, limit)
    print(json.dumps([m.__dict__ for m in models], indent=2))


def _install_model(model: str) -> None:
    ok = OllamaRegistry().download_model(model)
    print("installed" if ok else "failed")


async def _ingest_url(url: str) -> None:
    pipeline = SimpleRAGPipeline()
    chunks = await pipeline.ingest_website(url)
    print(f"ingested_chunks={chunks}")


async def _evaluate_model(
    model_name: str,
    categories: Optional[List[str]] = None,
    output_file: Optional[str] = None,
) -> None:
    """Evaluate a single model."""
    # Create model client
    client = FallbackLLMClient(targets=[{"provider": "ollama", "model": model_name}])

    async def model_fn(prompt: str) -> str:
        return await client.generate(prompt)

    # Run evaluation
    results = await quick_evaluate_model(model_fn, model_name, categories)

    if output_file:
        Path(output_file).parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"Results saved to {output_file}")
    else:
        print(json.dumps(results, indent=2))


async def _benchmark_models(
    model_names: List[str],
    categories: Optional[List[str]] = None,
    output_dir: str = "evaluation_reports",
) -> None:
    """Benchmark multiple models."""
    # Create model clients
    models = {}
    for model_name in model_names:
        client = FallbackLLMClient(targets=[{"provider": "ollama", "model": model_name}])

        async def model_fn(prompt: str, client=client) -> str:
            return await client.generate(prompt)

        models[model_name] = model_fn

    # Run benchmark
    benchmarker = ModelBenchmarker()
    results = await benchmarker.benchmark_models(
        models,
        categories=categories,
        save_reports=True,
        output_dir=output_dir,
    )

    # Print summary
    print(f"\nBenchmark Results (saved to {output_dir}/)")
    print("=" * 50)

    for model_name, metrics in results.items():
        print(f"\n📊 {model_name}")
        print("-" * 30)
        print(".4f")
        print(".4f")
        print(".4f")
        print(".4f")
        print(".4f")
        print(".2f")
        print(f"  Test Cases: {metrics['total_cases']}")

    # Show ranking
    if len(results) > 1:
        print("
🏆 Ranking by Correctness:"        ranking = sorted(results.items(), key=lambda x: x[1]['correctness'], reverse=True)
        for i, (model, _) in enumerate(ranking, 1):
            print(f"  {i}. {model}")


async def _run_custom_evaluation(
    test_file: str,
    model_name: str,
    output_file: Optional[str] = None,
) -> None:
    """Run evaluation with custom test cases."""
    # Load test cases
    with open(test_file, 'r') as f:
        test_data = json.load(f)

    cases = []
    for item in test_data:
        cases.append(EvaluationCase(**item))

    # Create model client
    client = FallbackLLMClient(targets=[{"provider": "ollama", "model": model_name}])

    async def model_fn(prompt: str) -> str:
        return await client.generate(prompt)

    # Run evaluation
    evaluator = LLMEvaluator()
    report = await evaluator.evaluate_model(model_fn, model_name, cases)

    if output_file:
        evaluator.save_report(report, output_file)
        print(f"Detailed report saved to {output_file}")
    else:
        # Print summary
        print(f"Evaluation Report for {model_name}")
        print("=" * 40)
        print(f"Total Cases: {report.total_cases}")
        print(".4f")
        print(".4f")
        print(".4f")
        print(".4f")
        print(".4f")
        print(".2f")


def _list_evaluation_categories() -> None:
    """List available evaluation categories."""
    from ai_devops_assistant.evaluation.benchmark import EvaluationTestSuite

    suite = EvaluationTestSuite()
    categories = suite.get_categories()

    print("Available Evaluation Categories:")
    print("=" * 35)

    for category in categories:
        cases = suite.get_test_cases([category])
        print(f"• {category}: {len(cases)} test cases")

    print(f"\nTotal: {len(suite.get_test_cases())} test cases across {len(categories)} categories")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="ai-devops",
        description="AI DevOps Assistant CLI"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Models command
    model_cmd = subparsers.add_parser("models", help="Model management")
    model_sub = model_cmd.add_subparsers(dest="action", help="Model actions")
    search = model_sub.add_parser("search", help="Search for models")
    search.add_argument("query", help="Search query")
    search.add_argument("--limit", type=int, default=10, help="Max results")
    install = model_sub.add_parser("install", help="Install a model")
    install.add_argument("model", help="Model name to install")

    # Ingest command
    ingest = subparsers.add_parser("ingest", help="Ingest content into RAG")
    ingest.add_argument("url", help="URL to ingest")

    # Evaluate command
    evaluate_cmd = subparsers.add_parser("evaluate", help="Evaluate LLM models")
    evaluate_sub = evaluate_cmd.add_subparsers(dest="eval_action", help="Evaluation actions")

    # Single model evaluation
    eval_single = evaluate_sub.add_parser("model", help="Evaluate a single model")
    eval_single.add_argument("model_name", help="Name of the model to evaluate")
    eval_single.add_argument(
        "--categories",
        nargs="*",
        help="Categories to test (default: all)"
    )
    eval_single.add_argument(
        "--output",
        help="Output file for results (JSON)"
    )

    # Multi-model benchmark
    benchmark = evaluate_sub.add_parser("benchmark", help="Benchmark multiple models")
    benchmark.add_argument(
        "model_names",
        nargs="+",
        help="Names of models to benchmark"
    )
    benchmark.add_argument(
        "--categories",
        nargs="*",
        help="Categories to test (default: all)"
    )
    benchmark.add_argument(
        "--output-dir",
        default="evaluation_reports",
        help="Directory to save reports"
    )

    # Custom evaluation
    eval_custom = evaluate_sub.add_parser("custom", help="Run custom evaluation")
    eval_custom.add_argument("test_file", help="JSON file with test cases")
    eval_custom.add_argument("model_name", help="Model to evaluate")
    eval_custom.add_argument(
        "--output",
        help="Output file for detailed report"
    )

    # List categories
    evaluate_sub.add_parser("categories", help="List available test categories")

    args = parser.parse_args()

    # Handle commands
    if args.command == "models":
        if args.action == "search":
            asyncio.run(_search_models(args.query, args.limit))
        elif args.action == "install":
            _install_model(args.model)
        else:
            model_cmd.print_help()

    elif args.command == "ingest":
        asyncio.run(_ingest_url(args.url))

    elif args.command == "evaluate":
        if args.eval_action == "model":
            asyncio.run(_evaluate_model(
                args.model_name,
                args.categories,
                args.output
            ))
        elif args.eval_action == "benchmark":
            asyncio.run(_benchmark_models(
                args.model_names,
                args.categories,
                args.output_dir
            ))
        elif args.eval_action == "custom":
            asyncio.run(_run_custom_evaluation(
                args.test_file,
                args.model_name,
                args.output
            ))
        elif args.eval_action == "categories":
            _list_evaluation_categories()
        else:
            evaluate_cmd.print_help()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
