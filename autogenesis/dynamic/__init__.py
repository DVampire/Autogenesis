"""Dynamic module management for runtime code execution and class/function loading.

This module provides utilities for dynamically creating Python modules and loading
classes/functions from source code strings. Useful for dynamically generated code
that doesn't exist in the filesystem.
"""

from .server import (
    DynamicModuleManager,
    dynamic_manager
)

__all__ = [
    "DynamicModuleManager",
    "dynamic_manager",
]

