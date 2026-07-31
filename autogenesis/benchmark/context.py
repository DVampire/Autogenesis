"""Benchmark Context Manager for managing benchmark lifecycle and resources with lazy loading."""
import os
from asyncio_atexit import register as async_atexit_register
from typing import Any, Dict, List, Type, Optional, Union, Tuple, TYPE_CHECKING
from datetime import datetime
import inflection
import json
from pydantic import BaseModel, ConfigDict, Field

from autogenesis.logger import logger
from autogenesis.config import config
from autogenesis.version import version_manager
from autogenesis.utils import (assemble_workspace_path,
                       gather_with_concurrency,
                       file_lock
                       )
from autogenesis.benchmark.types import BenchmarkConfig, Benchmark, Task, Stats
from autogenesis.dynamic import dynamic_manager
from autogenesis.registry import BENCHMARK

class BenchmarkContextManager(BaseModel):
    """Global context manager for all benchmarks with lazy loading support."""
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")
    
    base_dir: str = Field(default=None, description="The base directory to use for the benchmarks")
    
    def __init__(self, 
                 base_dir: Optional[str] = None,
                 **kwargs):
        """Initialize the benchmark context manager.
        
        Args:
            base_dir: Base directory for storing benchmark data
        """
        super().__init__(**kwargs)
        
        if base_dir is not None:
            self.base_dir = assemble_workspace_path(base_dir)
        else:
            self.base_dir = assemble_workspace_path(os.path.join(config.log_root, "benchmark"))
        logger.info(f"| 📁 Benchmark context manager base directory: {self.base_dir}.")    
        
        

        self._benchmark_configs: Dict[str, BenchmarkConfig] = {}  # Current active configs (latest version)
        self._benchmark_history_versions: Dict[str, Dict[str, BenchmarkConfig]] = {}
        
        self._cleanup_registered = False
    
    async def initialize(self, benchmark_names: Optional[List[str]] = None):
        """Initialize the benchmark context manager."""
        # Register benchmark-related symbols for auto-injection in dynamic code
        dynamic_manager.register_symbol("BENCHMARK", BENCHMARK)
        dynamic_manager.register_symbol("Benchmark", Benchmark)
        
        # Register benchmark context provider for automatic import injection
        def benchmark_context_provider():
            """Provide benchmark-related imports for dynamic benchmark classes."""
            return {
                "BENCHMARK": BENCHMARK,
                "Benchmark": Benchmark,
            }
        dynamic_manager.register_context_provider("benchmark", benchmark_context_provider)
        
        # Load benchmarks from BENCHMARK registry
        benchmark_configs = {}
        registry_benchmark_configs: Dict[str, BenchmarkConfig] = await self._load_from_registry()
        benchmark_configs.update(registry_benchmark_configs)
        
        # Load benchmarks from code (JSON file)
        code_benchmark_configs: Dict[str, BenchmarkConfig] = {}
        
        # Merge code configs with registry configs, only override if code version is strictly greater
        for benchmark_name, code_config in code_benchmark_configs.items():
            if benchmark_name in benchmark_configs:
                registry_config = benchmark_configs[benchmark_name]
                if version_manager.compare_versions(code_config.version, registry_config.version) > 0:
                    logger.info(f"| 🔄 Overriding benchmark {benchmark_name} from registry (v{registry_config.version}) with code version (v{code_config.version})")
                    benchmark_configs[benchmark_name] = code_config
                else:
                    logger.info(f"| 📌 Keeping benchmark {benchmark_name} from registry (v{registry_config.version}), code version (v{code_config.version}) is not greater")
                    if version_manager.compare_versions(code_config.version, registry_config.version) == 0:
                        if benchmark_name in self._benchmark_history_versions:
                            self._benchmark_history_versions[benchmark_name][registry_config.version] = registry_config
            else:
                benchmark_configs[benchmark_name] = code_config
        
        if benchmark_names is not None:
            benchmark_configs = {name: benchmark_configs[name] for name in benchmark_names if name in benchmark_configs}
        
        # Build all benchmark systems concurrently
        names_list = list(benchmark_configs.keys())
        tasks = [self.build(benchmark_configs[name]) for name in names_list]
        results = await gather_with_concurrency(tasks, max_concurrency=10, return_exceptions=True)

        for name, result in zip(names_list, results):
            if isinstance(result, Exception):
                logger.error(f"| ❌ Failed to initialize benchmark {name}: {result}")
                continue
            self._benchmark_configs[name] = result
            logger.info(f"| 🔧 Benchmark {name} initialized")
        
        # Save to JSON and contract
        
        # Register cleanup callback
        async_atexit_register(self.cleanup)
        self._cleanup_registered = True
        
        logger.info(f"| ✅ Benchmark systems initialization completed")

    async def _load_from_registry(self):
        """Load benchmarks from BENCHMARK registry."""
        benchmark_configs: Dict[str, BenchmarkConfig] = {}
        
        async def register_benchmark_class(benchmark_cls: Type[Benchmark]):
            try:
                # Get benchmark config from global config
                name_key = inflection.underscore(benchmark_cls.__name__)
                benchmark_config_dict = config.get(name_key, {})
                
                # Create temporary instance to get name and description
                try:
                    temp_instance = benchmark_cls(**benchmark_config_dict)
                    benchmark_name = temp_instance.name
                    benchmark_description = temp_instance.description
                except Exception:
                    benchmark_name = getattr(benchmark_cls, 'name', name_key)
                    benchmark_description = getattr(benchmark_cls, 'description', benchmark_cls.__doc__ or "")
                
                # Get version from version manager
                version = await version_manager.get_version("benchmark", benchmark_name)
                
                # Get module source code
                code = dynamic_manager.get_full_module_source(benchmark_cls)
                
                # Create benchmark config
                benchmark_config = BenchmarkConfig(
                    name=benchmark_name,
                    description=benchmark_description,
                    version=version,
                    cls=benchmark_cls,
                    config=benchmark_config_dict,
                    instance=None,
                    metadata={},
                    code=code,
                )
                
                benchmark_configs[benchmark_name] = benchmark_config
                if benchmark_name not in self._benchmark_history_versions:
                    self._benchmark_history_versions[benchmark_name] = {}
                self._benchmark_history_versions[benchmark_name][version] = benchmark_config
                
                await version_manager.register_version("benchmark", benchmark_name, version)
                logger.info(f"| 📝 Registered benchmark: {benchmark_name} ({benchmark_cls.__name__})")
            except Exception as e:
                logger.error(f"| ❌ Failed to register benchmark class {benchmark_cls.__name__}: {e}")
        
        import autogenesis.benchmark  # noqa: F401
        benchmark_classes = list(BENCHMARK._module_dict.values())
        tasks = [register_benchmark_class(cls) for cls in benchmark_classes]
        await gather_with_concurrency(tasks, max_concurrency=10, return_exceptions=True)
        
        return benchmark_configs

    async def register(self, 
                       benchmark: Union[Benchmark, Type[Benchmark]],
                       benchmark_config_dict: Optional[Dict[str, Any]] = None,
                       override: bool = False,
                       version: Optional[str] = None) -> BenchmarkConfig:
        """Register a benchmark class or instance."""
        try:
            if isinstance(benchmark, Benchmark):
                benchmark_instance = benchmark
                benchmark_cls = type(benchmark)
                if benchmark_config_dict:
                    raise ValueError("Extra configuration not allowed when registering benchmark instances.")
                benchmark_config_dict = {}
            else:
                benchmark_cls = benchmark
                if benchmark_config_dict is None:
                    name_key = inflection.underscore(benchmark_cls.__name__)
                    benchmark_config_dict = config.get(name_key, {})
                
                try:
                    benchmark_instance = benchmark_cls(**benchmark_config_dict)
                except Exception as e:
                    raise ValueError(f"Failed to instantiate benchmark {benchmark_cls.__name__}: {e}")
            
            benchmark_name = benchmark_instance.name
            benchmark_description = benchmark_instance.description
            
            if not benchmark_name:
                raise ValueError("Benchmark.name cannot be empty.")
            
            if benchmark_name in self._benchmark_configs and not override:
                raise ValueError(f"Benchmark '{benchmark_name}' already registered. Use override=True.")
            
            if version is None:
                version = await version_manager.get_version("benchmark", benchmark_name)
                
            code = dynamic_manager.get_full_module_source(benchmark_cls)
            
            benchmark_config = BenchmarkConfig(
                name=benchmark_name,
                description=benchmark_description,
                version=version,
                cls=benchmark_cls,
                config=benchmark_config_dict,
                instance=benchmark_instance if isinstance(benchmark, Benchmark) else None,
                metadata=getattr(benchmark_instance, 'metadata', {}),
                code=code,
            )
            
            self._benchmark_configs[benchmark_name] = benchmark_config
            if benchmark_name not in self._benchmark_history_versions:
                self._benchmark_history_versions[benchmark_name] = {}
            self._benchmark_history_versions[benchmark_name][version] = benchmark_config
            
            await version_manager.register_version("benchmark", benchmark_name, version)
            
            logger.info(f"| 📝 Registered benchmark config: {benchmark_name}: {version}")
            return benchmark_config
        except Exception as e:
            logger.error(f"| ❌ Failed to register benchmark: {e}")
            raise

    async def update(self, 
                     benchmark_name: str,
                     benchmark: Union[Benchmark, Type[Benchmark]],
                     benchmark_config_dict: Optional[Dict[str, Any]] = None,
                     new_version: Optional[str] = None, 
                     description: Optional[str] = None) -> BenchmarkConfig:
        """Update an existing benchmark and create a new version."""
        try:
            if isinstance(benchmark, Benchmark):
                benchmark_instance = benchmark
                benchmark_cls = type(benchmark)
                benchmark_config_dict = {}
            else:
                benchmark_cls = benchmark
                if benchmark_config_dict is None:
                    name_key = inflection.underscore(benchmark_cls.__name__)
                    benchmark_config_dict = config.get(name_key, {})
                benchmark_instance = benchmark_cls(**benchmark_config_dict)
            
            original_config = self._benchmark_configs.get(benchmark_name)
            if original_config is None:
                raise ValueError(f"Benchmark {benchmark_name} not found. Use register().")
            
            if new_version is None:
                new_version = await version_manager.generate_next_version("benchmark", benchmark_name, "patch")
            
            code = dynamic_manager.get_full_module_source(benchmark_cls)
            
            updated_config = BenchmarkConfig(
                name=benchmark_name,
                description=benchmark_instance.description,
                version=new_version,
                cls=benchmark_cls,
                config=benchmark_config_dict,
                instance=benchmark_instance,  # Always use the created instance
                metadata=getattr(benchmark_instance, 'metadata', {}),
                code=code,
            )
            
            self._benchmark_configs[benchmark_name] = updated_config
            if benchmark_name not in self._benchmark_history_versions:
                self._benchmark_history_versions[benchmark_name] = {}
            self._benchmark_history_versions[benchmark_name][new_version] = updated_config
            
            await version_manager.register_version(
                "benchmark", benchmark_name, new_version,
                description=description or f"Updated from {original_config.version}"
            )
            
            logger.info(f"| 🔄 Updated benchmark {benchmark_name} from v{original_config.version} to v{new_version}")
            return updated_config
        except Exception as e:
            logger.error(f"| ❌ Failed to update benchmark: {e}")
            raise

    async def build(self, config: BenchmarkConfig) -> BenchmarkConfig:
        """Create a benchmark instance and store it."""
        if config.name in self._benchmark_configs:
            existing = self._benchmark_configs[config.name]
            if existing.instance is not None:
                return existing
        
        try:
            if config.cls is None:
                raise ValueError(f"No class provided for {config.name}")
            
            instance = config.cls(**config.config) if config.config else config.cls()
            if hasattr(instance, "initialize"):
                await instance.initialize()
            
            config.instance = instance
            self._benchmark_configs[config.name] = config
            return config
        except Exception as e:
            logger.error(f"| ❌ Failed to create benchmark {config.name}: {e}")
            raise

    async def get(self, name: str) -> Optional[Benchmark]:
        """Get benchmark instance by name."""
        config = self._benchmark_configs.get(name)
        return config.instance if config else None

    async def restore(self, name: str, version: str, auto_initialize: bool = True) -> Optional[BenchmarkConfig]:
        """Restore a specific version of a benchmark."""
        version_config = None
        if name in self._benchmark_history_versions:
            version_config = self._benchmark_history_versions[name].get(version)
        
        if version_config is None:
            logger.warning(f"| ⚠️ Version {version} not found for benchmark {name}")
            return None
        
        restored_config = BenchmarkConfig(**version_config.model_dump())
        self._benchmark_configs[name] = restored_config
        
        version_history = await version_manager.get_version_history("benchmark", name)
        if version_history:
            if version not in version_history.versions:
                await version_manager.register_version("benchmark", name, version)
            version_history.current_version = version
        else:
            await version_manager.register_version("benchmark", name, version)
        
        if auto_initialize and restored_config.cls is not None:
            await self.build(restored_config)
        
        logger.info(f"| 🔄 Restored benchmark {name} to version {version}")
        return restored_config

    async def cleanup(self):
        """Cleanup active benchmarks."""
        for name, config in self._benchmark_configs.items():
            if config.instance is not None and hasattr(config.instance, "cleanup"):
                try:
                    await config.instance.cleanup()
                except Exception as e:
                    logger.warning(f"| ⚠️ Error during benchmark {name} cleanup: {e}")
        
        self._benchmark_configs.clear()
        self._benchmark_history_versions.clear()
        logger.info("| 🧹 Benchmark context manager cleaned up")

    async def reset(self, name: str, split: Optional[str] = None) -> Optional[Task]:
        """Reset benchmark progress (delegates to benchmark instance)."""
        instance = await self.get(name)
        if instance is None:
            raise ValueError(f"Benchmark '{name}' not found")
        # Update split if provided
        if split is not None and hasattr(instance, 'split'):
            instance.split = split
            # Re-initialize benchmark with new split
            if hasattr(instance, "initialize"):
                await instance.initialize()
        return await instance.reset()

    async def step(self, name: str) -> Optional[Task]:
        """Get next benchmark task (delegates to benchmark instance)."""
        instance = await self.get(name)
        if instance is None:
            raise ValueError(f"Benchmark '{name}' not found")
        return await instance.step()

    async def eval(self, name: str, task: Task) -> Optional[Task]:
        """Evaluate a benchmark task (delegates to benchmark instance)."""
        instance = await self.get(name)
        if instance is None:
            raise ValueError(f"Benchmark '{name}' not found")
        return await instance.eval(task)

    async def stats(self, name: str) -> Optional[Stats]:
        """Get benchmark statistics (delegates to benchmark instance)."""
        instance = await self.get(name)
        if instance is None:
            raise ValueError(f"Benchmark '{name}' not found")
        return await instance.stats()
