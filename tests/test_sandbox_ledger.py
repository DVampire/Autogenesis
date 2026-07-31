"""Crash-safe sandbox ledger: record/forget roundtrip and stale reaping."""

from __future__ import annotations

import asyncio

from autogenesis.sandbox.ledger import ledger


def _use_home(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AUTOGENESIS_HOME", str(tmp_path))


def test_record_forget_roundtrip(monkeypatch, tmp_path) -> None:
    _use_home(monkeypatch, tmp_path)
    assert ledger.stale_ids() == []
    ledger.record("aaa")
    ledger.record("bbb")
    ledger.record("aaa")  # idempotent
    assert ledger.stale_ids() == ["aaa", "bbb"]
    ledger.forget("aaa")
    assert ledger.stale_ids() == ["bbb"]
    ledger.forget("missing")  # no-op
    assert ledger.stale_ids() == ["bbb"]


def test_reap_stale_removes_recorded_containers(monkeypatch, tmp_path) -> None:
    _use_home(monkeypatch, tmp_path)
    ledger.record("dead-1")
    ledger.record("sandbox-dead-2")  # already-prefixed ids are used as-is
    removed: list[str] = []

    async def fake_remove(name: str) -> bool:
        removed.append(name)
        return True

    monkeypatch.setattr(ledger, "_remove_container", fake_remove)
    reaped = asyncio.run(ledger.reap_stale())
    assert sorted(reaped) == ["sandbox-dead-1", "sandbox-dead-2"]
    assert sorted(removed) == ["sandbox-dead-1", "sandbox-dead-2"]
    # Ledger is cleared afterwards; a second reap is a no-op.
    assert ledger.stale_ids() == []
    assert asyncio.run(ledger.reap_stale()) == []


def test_reap_stale_keeps_entries_when_removal_fails(monkeypatch, tmp_path) -> None:
    _use_home(monkeypatch, tmp_path)
    ledger.record("dead-3")

    async def broken_remove(_name: str) -> bool:
        raise FileNotFoundError("no docker socket and no CLI")

    monkeypatch.setattr(ledger, "_remove_container", broken_remove)
    assert asyncio.run(ledger.reap_stale()) == []
    # Entries stay recorded so a later boot (with docker available) can reap.
    assert ledger.stale_ids() == ["dead-3"]
