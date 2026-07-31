import pytest

from autogenesis.cli import gateway_main


def test_public_gateway_requires_token(monkeypatch) -> None:
    monkeypatch.delenv("AUTOGENESIS_GATEWAY_TOKEN", raising=False)
    with pytest.raises(SystemExit) as exc:
        gateway_main(["--transport", "websocket", "--host", "0.0.0.0"])
    assert exc.value.code == 2
