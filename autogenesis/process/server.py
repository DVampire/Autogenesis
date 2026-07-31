"""Process Manager — a lightweight registry-backed manager for pure processors.

Mirrors :class:`autogenesis.plugins.server.PluginManagerServer`: build processor
instances once from the :data:`PROCESS` registry and invoke by name. ``__call__``
returns a :class:`Response` the workflow runtime normalizes to
``{message, data, files}``.
"""

from typing import Any, Dict, List, Optional

import inflection
from pydantic import BaseModel, ConfigDict

from autogenesis.config import config
from autogenesis.logger import logger
from autogenesis.registry import PROCESS
from autogenesis.response.types import Response, ResponseType
from autogenesis.process.types import Processor, ProcessContext


class ProcessManager(BaseModel):
    """Manages pure-processor registration and invocation."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._processors: Dict[str, Processor] = {}

    async def initialize(self, process_names: Optional[List[str]] = None) -> None:
        """Build processor instances from the PROCESS registry."""
        import autogenesis.process  # noqa: F401 — ensure default processors register

        for cls in list(PROCESS._module_dict.values()):
            try:
                name_key = inflection.underscore(cls.__name__)
                cfg = config.get(name_key, {}) or {}
                instance: Processor = cls(**cfg) if cfg else cls()
                if not instance.name:
                    instance.name = name_key
                if process_names is not None and instance.name not in process_names:
                    continue
                self._processors[instance.name] = instance
                logger.info(f"| ⚙️ Registered processor: {instance.name}")
            except Exception as e:  # noqa: BLE001 — a broken processor must not abort startup
                logger.error(f"| ❌ Failed to initialize processor {cls.__name__}: {e}")
        logger.info("| ✅ Processors initialization completed")

    async def list(self) -> List[str]:
        """List registered processor names."""
        return list(self._processors.keys())

    async def list_infos(self) -> List[Processor]:
        """Return every registered processor instance (for catalog/roster building)."""
        return list(self._processors.values())

    async def get(self, name: str) -> Optional[Processor]:
        """Get a processor instance by name."""
        return self._processors.get(name)

    async def get_info(self, name: str) -> Optional[Processor]:
        """Get a processor's descriptor (the instance doubles as its info)."""
        return self._processors.get(name)

    async def get_schema(self, name: str, action: Optional[str] = None, format: str = "json"):
        """Processors accept free-form params; no strict call schema (yet)."""
        return None

    async def register(self, processor: Processor, override: bool = False) -> Processor:
        """Register a processor instance directly (used by tests/extensions)."""
        if processor.name in self._processors and not override:
            raise ValueError(f"Processor '{processor.name}' already registered. Use override=True.")
        self._processors[processor.name] = processor
        return processor

    async def __call__(self, name: str, input: Dict[str, Any], ctx: ProcessContext = None, **kwargs) -> Response:
        """Invoke a processor by name; failures come back as an unsuccessful Response."""
        processor = self._processors.get(name)
        if processor is None:
            return Response(type=ResponseType.TOOL, success=False, message=f"Unknown processor: {name}")
        try:
            return await processor(**(input or {}))
        except Exception as e:  # noqa: BLE001 — a bad transform is a failed result, not a crash
            logger.error(f"| ❌ Processor {name} failed: {e}")
            return Response(type=ResponseType.TOOL, success=False, message=f"Processor {name} failed: {e}")

    async def cleanup(self) -> None:
        """Clear registered processors (they hold no external resources)."""
        self._processors.clear()


process_manager = ProcessManager()
