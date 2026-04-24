"""CLI for model management, RAG ingestion, and evaluation."""

from __future__ import annotations

import argparse
import asyncio
import json

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


async def _evaluate() -> None:
    evaluator = LLMEvaluator()
    client = FallbackLLMClient(targets=[{"provider": "ollama", "model": "llama3"}])
    cases = [
        EvaluationCase(
            prompt="How do I check pod health in Kubernetes?",
            expected_keywords=["kubectl", "get pods", "health"],
        )
    ]
    report = await evaluator.evaluate(client.generate, cases)
    print(json.dumps(report, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(prog="ai-devops")
    subparsers = parser.add_subparsers(dest="command")

    model_cmd = subparsers.add_parser("models")
    model_sub = model_cmd.add_subparsers(dest="action")
    search = model_sub.add_parser("search")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=10)
    install = model_sub.add_parser("install")
    install.add_argument("model")

    ingest = subparsers.add_parser("ingest")
    ingest.add_argument("url")

    subparsers.add_parser("evaluate")

    args = parser.parse_args()
    if args.command == "models" and args.action == "search":
        asyncio.run(_search_models(args.query, args.limit))
        return
    if args.command == "models" and args.action == "install":
        _install_model(args.model)
        return
    if args.command == "ingest":
        asyncio.run(_ingest_url(args.url))
        return
    if args.command == "evaluate":
        asyncio.run(_evaluate())
        return
    parser.print_help()


if __name__ == "__main__":
    main()
