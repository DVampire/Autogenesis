import os
import sys
import socket
from urllib.parse import urlparse

try:
    import hvac
except ImportError:  # Vault is optional; environment variables remain supported.
    hvac = None
from dotenv import load_dotenv

load_dotenv(verbose=True)

# Short timeout (seconds) for probing / talking to Vault. Kept small so that a
# down or unreachable Vault never blocks startup -- we fall back to .env fast.
_VAULT_TIMEOUT = float(os.environ.get("VAULT_TIMEOUT", "1.5"))


def _vault_running(url: str, timeout: float = _VAULT_TIMEOUT) -> bool:
    """Cheaply check whether a Vault server is actually listening at ``url``.

    Does a plain TCP connect to the host:port from ``VAULT_ADDR`` with a short
    timeout. This avoids handing a dead address to hvac, whose underlying HTTP
    request can otherwise hang and stall startup.
    """
    try:
        parsed = urlparse(url)
        host = parsed.hostname
        if not host:
            return False
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


class VaultClient:
    """Secret accessor that prefers Vault when available and falls back to env.

    If Vault (VAULT_ADDR / VAULT_TOKEN / SECRET_ENGINE_PATH) is configured and
    reachable, secrets are read from the secret engine. Otherwise the client
    operates in env-only mode and reads values straight from ``os.environ``,
    which ``load_dotenv`` has already populated from ``.env``.
    """

    def __init__(self, url: str = None, token: str = None, secret_engine_path: str = None):
        url = url or os.environ.get("VAULT_ADDR")
        token = token or os.environ.get("VAULT_TOKEN")
        self._path = secret_engine_path or os.environ.get("SECRET_ENGINE_PATH")
        self._client = None
        self._cache: dict | None = None

        if url and token and self._path:
            if hvac is None:
                print("[VaultClient] hvac is not installed; using secrets from .env / environment.", file=sys.stderr)
                return
            # 1) Probe first: if no Vault process is listening, skip hvac
            #    entirely and use .env -- never risk a hanging request.
            if not _vault_running(url):
                print(
                    f"[VaultClient] Vault not reachable at {url}; "
                    f"using secrets from .env / environment.",
                    file=sys.stderr,
                )
                return
            # 2) Vault is up -> authenticate (with a short timeout as a guard).
            try:
                client = hvac.Client(url=url, token=token, timeout=_VAULT_TIMEOUT)
                if client.is_authenticated():
                    self._client = client
                else:
                    print(
                        "[VaultClient] Vault reachable but authentication failed; "
                        "using secrets from .env / environment.",
                        file=sys.stderr,
                    )
            except Exception:
                # Vault unreachable / misconfigured -> fall back to env.
                self._client = None

    @property
    def enabled(self) -> bool:
        """Whether secrets are being served from Vault."""
        return self._client is not None

    def _read(self) -> dict:
        """Fetch secrets from Vault, using cache if already loaded."""
        if self._cache is None:
            if not self.enabled:
                self._cache = {}
            else:
                result = self._client.read(self._path)
                if result is None:
                    raise KeyError(f"Vault path not found: {self._path}")
                self._cache = result["data"]
        return self._cache

    def register(self, *keys: str) -> None:
        """Read specified keys from Vault and register them as environment variables.

        In env-only mode this is a no-op since the keys already come from ``.env``.
        """
        if not self.enabled:
            return
        data = self._read()
        for key in keys:
            if key not in data:
                raise KeyError(f"Key '{key}' not found in Vault path '{self._path}'")
            os.environ[key] = data[key].strip()

    def register_all(self) -> None:
        """Read all keys from Vault and register them as environment variables.

        In env-only mode this is a no-op since the keys already come from ``.env``.
        """
        if not self.enabled:
            return
        for key, value in self._read().items():
            os.environ[key] = value.strip()

    def get(self, key: str) -> str:
        """Retrieve a single value by key.

        Reads from Vault when enabled, otherwise from the environment (``.env``).
        Falls back to the environment when a key is absent from Vault.
        """
        if self.enabled:
            values = self._read()
            if key in values:
                return values[key].strip()
        return os.environ.get(key, "").strip()


hvac_client = VaultClient()
hvac_client.register_all()
