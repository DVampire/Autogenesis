from typing import List, Optional
from pydantic import BaseModel, Field


class ManifestComponent(BaseModel):
    """One active extension component."""
    module: str = Field(description="Owning module: tool / agent / prompt / skill / environment")
    name: str = Field(description="Registered name (the key used to unregister)")
    version: str = Field(default="1.0.0", description="Currently active version of this component")
    file: str = Field(description="Active file/dir path relative to the extension root, e.g. 'tool/calculator_tool.py'")


class Manifest(BaseModel):
    """The single source of truth for the active extension set.

    Maps each active component to the version currently live and the flat working
    file that holds its source. All historical versions of a component coexist under
    `.versions/<module>/<name>/` — this manifest only names the active one.
    """
    components: List[ManifestComponent] = Field(default_factory=list)

    def find(self, module: str, name: str) -> Optional[ManifestComponent]:
        for c in self.components:
            if c.module == module and c.name == name:
                return c
        return None

    def upsert(self, comp: ManifestComponent) -> None:
        self.components = [c for c in self.components if not (c.module == comp.module and c.name == comp.name)]
        self.components.append(comp)

    def remove(self, module: str, name: str) -> None:
        self.components = [c for c in self.components if not (c.module == module and c.name == name)]
