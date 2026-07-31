"""Built-in sandbox backends. Importing this registers them with ``SANDBOX``."""

from .base import OpenSandbox
from .playwright import PlaywrightSandbox
from .chrome_vnc import ChromeVncSandbox
from .vscode import VscodeSandbox
from .host import HostSandbox

__all__ = [
    "OpenSandbox", "PlaywrightSandbox",
    "ChromeVncSandbox", "VscodeSandbox", "HostSandbox",
]
