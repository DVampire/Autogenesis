"""Benchmark Manager implementation"""
import os
from typing import Any, Dict, List, Optional, Union, Type
from pydantic import BaseModel, ConfigDict, Field

from autogenesis.config import config
from autogenesis.utils import assemble_workspace_path
from autogenesis.logger import logger
from autogenesis.benchmark.types import BenchmarkConfig, Benchmark, Task, Stats
from autogenesis.benchmark.context import BenchmarkContextManager

class BenchmarkManager(BaseModel):
    """Benchmark Manager for managing benchmark registration and lifecycle"""
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")
    
    base_dir: str = Field(default=None, description="Base directory for benchmarks")
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._registered_benchmarks: Dict[str, BenchmarkConfig] = {}

    async def initialize(self, benchmark_names: Optional[List[str]] = None):
        """Initialize benchmarks."""
        self.base_dir = assemble_workspace_path(os.path.join(config.log_root, "benchmark"))
        
        self.benchmark_context_manager = BenchmarkContextManager(
            base_dir=self.base_dir,
        )
        await self.benchmark_context_manager.initialize(benchmark_names=benchmark_names)
        logger.info("| ✅ Benchmark systems initialization completed")

    async def register(self, 
                       benchmark: Union[Benchmark, Type[Benchmark]], 
                       *, 
                       override: bool = False, 
                       **kwargs: Any) -> BenchmarkConfig:
        """Register a benchmark system asynchronously."""
        benchmark_config = await self.benchmark_context_manager.register(benchmark, override=override, **kwargs)
        self._registered_benchmarks[benchmark_config.name] = benchmark_config
        return benchmark_config

    async def update(self, 
                     benchmark_name: str, 
                     benchmark: Union[Benchmark, Type[Benchmark]], 
                     new_version: Optional[str] = None, 
                     description: Optional[str] = None,
                     **kwargs: Any) -> BenchmarkConfig:
        """Update an existing benchmark system."""
        benchmark_config = await self.benchmark_context_manager.update(benchmark_name, benchmark, new_version, description, **kwargs)
        self._registered_benchmarks[benchmark_config.name] = benchmark_config
        return benchmark_config

    async def get_info(self, benchmark_name: str) -> Optional[BenchmarkConfig]:
        """Get benchmark configuration by name."""
        return self.benchmark_context_manager._benchmark_configs.get(benchmark_name)

    async def list(self) -> List[str]:
        """List all registered benchmarks."""
        return list(self.benchmark_context_manager._benchmark_configs.keys())

    async def get(self, name: str) -> Optional[Benchmark]:
        """Get benchmark instance by name."""
        return await self.benchmark_context_manager.get(name)

    async def reset(self, name: str, split: Optional[str] = None) -> Optional[Task]:
        """Reset benchmark progress."""
        return await self.benchmark_context_manager.reset(name, split)

    async def step(self, name: str) -> Optional[Task]:
        """Get next benchmark task."""
        return await self.benchmark_context_manager.step(name)

    async def eval(self, name: str, task: Task) -> Optional[Task]:
        """Evaluate a benchmark task."""
        return await self.benchmark_context_manager.eval(name, task)

    async def stats(self, name: str) -> Optional[Stats]:
        """Get benchmark statistics."""
        return await self.benchmark_context_manager.stats(name)

    async def restore(self, name: str, version: str) -> Optional[BenchmarkConfig]:
        """Restore a specific version of a benchmark."""
        benchmark_config = await self.benchmark_context_manager.restore(name, version)
        if benchmark_config:
            self._registered_benchmarks[name] = benchmark_config
        return benchmark_config

    async def __call__(self, benchmark_name: str, results: List[Dict[str, str]], concurrency: int = 10) -> float:
        """Batch evaluation entry point"""
        benchmark = await self.get(benchmark_name)
        if not benchmark:
            raise RuntimeError(f"Benchmark {benchmark_name} not initialized.")
            
        import asyncio
        sem = asyncio.Semaphore(concurrency)

        async def _safe_eval(res):
            async with sem:
                t_id = str(res.get("task_id", ""))
                pred = res.get("prediction", "")
                gt = res.get("ground_truth")
                
                if not t_id:
                    return 0.0
                
                try:
                    # Create a Task object for evaluation
                    task = Task(
                        task_id=t_id,
                        result=pred,
                        ground_truth=gt
                    )
                    evaluated_task = await benchmark.eval(task)
                    return evaluated_task.score if evaluated_task else 0.0
                except Exception as e:
                    logger.error(f"| ❌ Eval failed for task {t_id}: {e}")
                    return 0.0

        tasks = [_safe_eval(res) for res in results]
        logger.info(f"| 🚀 Starting batch evaluation for {len(tasks)} items in benchmark '{benchmark_name}'")
        scores = await asyncio.gather(*tasks)
        
        avg_score = sum(scores) / len(scores) if scores else 0.0
        logger.info(f"| ✅ Batch evaluation for '{benchmark_name}' completed. Avg score: {avg_score:.4f}")
        return avg_score

    async def cleanup(self):
        """Cleanup all benchmarks using context manager."""
        if hasattr(self, 'benchmark_context_manager'):
            await self.benchmark_context_manager.cleanup()

# Global instance
benchmark_manager = BenchmarkManager()
