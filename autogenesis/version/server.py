"""Version Manager

Unified version management system for agents and tools.
Supports version tracking, evolution, and history management.
"""

from typing import Any, Dict, List, Optional, TypeVar

from pydantic import BaseModel, ConfigDict

from autogenesis.logger import logger
from autogenesis.version.types import ComponentVersionHistory

T = TypeVar('T', bound=BaseModel)



class VersionManagerServer(BaseModel):
    """Unified version manager server for all components - only manages version records"""
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    def __init__(self, **kwargs):
        """Initialize version manager"""
        super().__init__(**kwargs)
        
        # Storage: component_type -> name -> ComponentVersionHistory
        self._version_histories: Dict[str, Dict[str, ComponentVersionHistory]] = {
            "tool": {},
            "agent": {},
            "prompt": {},
            "memory": {},
            "benchmark": {},
            "skill": {},
            "connector": {},
            "environment": {},
            "plugin": {},
            "action": {},
            "constraint": {},
            "workflow": {},
        }

    async def initialize(self):
        """Initialize version manager.

        Version histories are kept in memory only — consistent with the other
        component managers (tool/agent/skill/connector/environment), which no
        longer persist to JSON. Retained as an awaitable no-op for callers.
        """
        logger.info("| 📁 Version manager initialized (in-memory).")
    
    async def register_version(self, component_type: str, name: str, version: str,
                        description: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> ComponentVersionHistory:
        """Register a version record (only version info, no config)
        
        Args:
            component_type: Type of component (tool, agent, prompt, memory, benchmark, skill)
            name: Component name
            version: Version string
            description: Version description
            metadata: Version metadata
            
        Returns:
            ComponentVersionHistory: Version history for the component
        """
        if component_type not in self._version_histories:
            raise ValueError(f"Unknown component type: {component_type}")
        
        if name not in self._version_histories[component_type]:
            version_history = ComponentVersionHistory(
                name=name,
                component_type=component_type,
                current_version=version
            )
            self._version_histories[component_type][name] = version_history
        else:
            version_history = self._version_histories[component_type][name]
        
        version_history.add_version(version, description, metadata)

        return version_history
    
    async def list(self) -> Dict[str, Dict[str, List[str]]]:
        """List all versions for all components
        
        Returns:
            Dictionary mapping component_type -> component_name -> list of versions
        """
        result = {}
        for component_type, histories in self._version_histories.items():
            result[component_type] = {}
            for name, version_history in histories.items():
                result[component_type][name] = version_history.list_versions()
        return result
    
    async def get_version_history(self, component_type: str, name: str) -> Optional[ComponentVersionHistory]:
        """Get version history for a component
        
        Args:
            component_type: Type of component
            name: Component name
            
        Returns:
            ComponentVersionHistory or None if not found
        """
        if component_type not in self._version_histories:
            return None
        
        return self._version_histories[component_type].get(name)
    
    async def get_current_version(self, component_type: str, name: str) -> Optional[str]:
        """Get current version for a component
        
        Args:
            component_type: Type of component
            name: Component name
            
        Returns:
            Current version string or None if not found
        """
        version_history = await self.get_version_history(component_type, name)
        if version_history is None:
            return None
        return version_history.current_version
    
    async def generate_next_version(self, component_type: str, name: str, 
                                   version_type: str = "patch") -> str:
        """Generate next version number for a component
        
        Args:
            component_type: Type of component (tool, agent, prompt, memory, benchmark, skill)
            name: Component name
            version_type: Type of version increment ("major", "minor", "patch")
            
        Returns:
            Next version string (e.g., "1.0.1", "1.1.0", "2.0.0")
        """
        current_version = await self.get_current_version(component_type, name)
        
        if current_version is None:
            # First version
            return "1.0.0"
        
        try:
            # Parse current version (e.g., "1.2.3")
            version_parts = current_version.split(".")
            if len(version_parts) >= 3:
                major = int(version_parts[0])
                minor = int(version_parts[1])
                patch = int(version_parts[2])
            elif len(version_parts) == 2:
                major = int(version_parts[0])
                minor = int(version_parts[1])
                patch = 0
            elif len(version_parts) == 1:
                major = int(version_parts[0])
                minor = 0
                patch = 0
            else:
                # Invalid version format, start fresh
                return "1.0.0"
            
            # Increment based on version_type
            if version_type == "major":
                major += 1
                minor = 0
                patch = 0
            elif version_type == "minor":
                minor += 1
                patch = 0
            else:  # patch (default)
                patch += 1
            
            return f"{major}.{minor}.{patch}"
            
        except (ValueError, IndexError):
            # If version parsing fails, start fresh
            logger.warning(f"| ⚠️ Failed to parse version {current_version} for {component_type}/{name}, starting fresh")
            return "1.0.0"
    
    async def get_version(self, 
                          component_type: str, 
                          name: str, 
                          provided_version: Optional[str] = None) -> str:
        """Get version from version_manager or generate new one
        
        Args:
            component_type: Type of component (tool, agent, prompt, memory, benchmark, skill)
            name: Component name
            provided_version: Version provided by user (if any)
            
        Returns:
            Version string to use
        """
        if provided_version:
            # Use provided version
            return provided_version
        
        # Check if component already exists
        current_version = await self.get_current_version(component_type, name)
        if current_version is None:
            # New component, start with 1.0.0
            return "1.0.0"
        else:
            # Existing component, generate next patch version
            return await self.generate_next_version(component_type, name, "patch")
    
    async def deprecate_version(self, component_type: str, name: str, version: str):
        """Deprecate a version for a component
        
        Args:
            component_type: Type of component
            name: Component name
            version: Version string to deprecate
        """
        version_history = await self.get_version_history(component_type, name)
        if version_history is None:
            raise ValueError(f"Component {component_type}/{name} not found")
        
        version_history.deprecate_version(version)

    async def archive_version(self, component_type: str, name: str, version: str):
        """Archive a version for a component
        
        Args:
            component_type: Type of component
            name: Component name
            version: Version string to archive
        """
        version_history = await self.get_version_history(component_type, name)
        if version_history is None:
            raise ValueError(f"Component {component_type}/{name} not found")
        
        version_history.archive_version(version)

    @staticmethod
    def compare_versions(v1: str, v2: str) -> int:
        """Compare two version strings. Returns 1 if v1 > v2, -1 if v1 < v2, 0 if equal.
        
        Args:
            v1: First version string (e.g., "1.0.0")
            v2: Second version string (e.g., "1.0.1")
            
        Returns:
            1 if v1 > v2, -1 if v1 < v2, 0 if equal
        """
        try:
            parts1 = [int(x) for x in v1.split(".")]
            parts2 = [int(x) for x in v2.split(".")]
            
            # Pad with zeros to same length
            max_len = max(len(parts1), len(parts2))
            parts1.extend([0] * (max_len - len(parts1)))
            parts2.extend([0] * (max_len - len(parts2)))
            
            for p1, p2 in zip(parts1, parts2):
                if p1 > p2:
                    return 1
                elif p1 < p2:
                    return -1
            return 0
        except:
            # Fallback: string comparison
            return 1 if v1 > v2 else (-1 if v1 < v2 else 0)


# Global version manager server instance
version_manager = VersionManagerServer()
