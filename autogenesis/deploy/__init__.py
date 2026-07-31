"""Deployment subsystem — run web services in sandboxes and bind them to URLs.

Public API::

    from autogenesis.deploy import deployment_manager, DeployRequest
    rec = await deployment_manager.deploy(DeployRequest(site_id="coffee", runtime="static", source_dir="..."))
    print(rec.url)
"""

from .types import (
    Deployer,
    DeploymentSpec,
    DeployRequest,
    HealthCheck,
    ResourceSpec,
    SiteRecord,
    SiteStatus,
)
from .server import deployment_manager, DeploymentManagerServer
from .default import *  # register built-in profiles

__all__ = [
    "Deployer",
    "DeploymentSpec",
    "DeployRequest",
    "HealthCheck",
    "ResourceSpec",
    "SiteRecord",
    "SiteStatus",
    "deployment_manager",
    "DeploymentManagerServer",
]
