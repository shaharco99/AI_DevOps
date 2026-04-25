"""Model benchmarking utilities."""

from ai_devops_assistant.benchmarking.model_benchmark import (
    AdvancedModelBenchmark,
    benchmark_model,  # Backward compatibility
)

# Backward compatibility alias
ModelBenchmark = AdvancedModelBenchmark

__all__ = ["AdvancedModelBenchmark", "ModelBenchmark", "benchmark_model"]
