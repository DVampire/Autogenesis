from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field

from autogenesis.logger import logger

class VersionStatus(str, Enum):
    """Version status"""
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class VersionInfo(BaseModel):
    """Version information"""
    version: str = Field(description="Version string (e.g., '1.0.0', '2.1.3')")
    status: VersionStatus = Field(default=VersionStatus.ACTIVE, description="Version status")
    created_at: datetime = Field(default_factory=datetime.now, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.now, description="Last update timestamp")
    description: Optional[str] = Field(default=None, description="Version description")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Version metadata")


class ComponentVersionHistory(BaseModel):
    """Version history for a component (only version records, no configs)"""
    name: str = Field(description="Name of the component")
    component_type: str = Field(description="Type of component (tool, environment, agent)")
    current_version: str = Field(description="Current active version")
    versions: Dict[str, VersionInfo] = Field(default_factory=dict, description="Version history records")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Component metadata")
    
    def add_version(self, version: str, description: Optional[str] = None, 
                   metadata: Optional[Dict[str, Any]] = None) -> VersionInfo:
        """Add a new version record
        
        Args:
            version: Version string
            description: Version description
            metadata: Version metadata
            
        Returns:
            VersionInfo: Created version info
        """
        if version in self.versions:
            logger.warning(f"| ⚠️ Version {version} already exists for {self.name}, updating...")
            version_info = self.versions[version]
            version_info.updated_at = datetime.now()
            if description:
                version_info.description = description
            if metadata:
                version_info.metadata.update(metadata)
        else:
            version_info = VersionInfo(
                version=version,
                description=description,
                metadata=metadata or {}
            )
            self.versions[version] = version_info
        
        self.current_version = version
        
        logger.debug(f"| ✅ Added version record {version} for {self.name}")
        return version_info
    
    def list_versions(self) -> List[str]:
        """List all available versions
        
        Returns:
            List of version strings
        """
        return list(self.versions.keys())
    
    def deprecate_version(self, version: str):
        """Deprecate a version
        
        Args:
            version: Version string to deprecate
        """
        if version not in self.versions:
            raise ValueError(f"Version {version} not found for {self.name}")
        
        if version == self.current_version:
            raise ValueError(f"Cannot deprecate current version {version}")
        
        self.versions[version].status = VersionStatus.DEPRECATED
        logger.info(f"| 📝 Deprecated version {version} for {self.name}")
    
    def archive_version(self, version: str):
        """Archive a version
        
        Args:
            version: Version string to archive
        """
        if version not in self.versions:
            raise ValueError(f"Version {version} not found for {self.name}")
        
        self.versions[version].status = VersionStatus.ARCHIVED
        logger.info(f"| 📦 Archived version {version} for {self.name}")