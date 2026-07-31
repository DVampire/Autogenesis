"""Docker sandbox backend (scaffold). See src/sandbox for the implemented backend."""

from .server import docker_manager

__all__ = ["docker_manager"]
