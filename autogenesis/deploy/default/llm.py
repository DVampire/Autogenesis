"""LLM inference deployer — PLACEHOLDER (not implemented yet).

LLM serving (vLLM/TGI/etc.) needs GPU passthrough, large weights, long warmup,
and API-style (not browser) readiness checks. The sandbox backend does not yet
expose GPU/resource controls (see ResourceSpec.gpu), so this profile is
registered as a known target type but intentionally not functional. It will be
filled in once GPU-capable sandboxing is available.
"""

from __future__ import annotations

from autogenesis.registry import DEPLOYER
from autogenesis.deploy.types import Deployer, DeploymentSpec, DeployRequest


@DEPLOYER.register_module(name="llm", force=True)
class LLMDeployer(Deployer):
    name = "llm"
    description = "Deploy an LLM inference service (vLLM/TGI). Not implemented yet — GPU sandbox support pending."
    default_image = "vllm/vllm-openai:latest"
    default_port = 8000

    def make_spec(self, request: DeployRequest) -> DeploymentSpec:
        raise NotImplementedError(
            "The 'llm' deploy profile is not implemented yet: it needs GPU passthrough, "
            "model-weight provisioning, and API-style readiness — pending GPU-capable sandbox "
            "support. Use runtime='custom' if you want to wire an inference server manually."
        )
