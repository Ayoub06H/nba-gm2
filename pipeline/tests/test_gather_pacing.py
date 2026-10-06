"""Throttle handling in gather.py, with a fake server and no real waiting."""

import pytest

import gather
from nbagm import plan
from nbagm.rawstore import RawStore


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    slept = []
    monkeypatch.setattr(gather.time, "sleep", lambda s: slept.append(s))
    return slept


def reqs(n):
    return [plan.Request(f"r{i}", "playbyplayv3", {"game_id": f"g{i}"}) for i in range(n)]


def test_throttle_window_triggers_one_cooldown_then_continues(tmp_path, monkeypatch, no_sleep):
    answers = iter([True, False, False, False, True, True])   # 3 failures in a row, then recovery
    monkeypatch.setattr(gather, "fetch",
                        lambda req: {"ok": 1} if next(answers) else (_ for _ in ()).throw(RuntimeError("empty")))
    store = RawStore(tmp_path / "c.sqlite")
    pacer = gather.Pacer()
    failed = gather.run(store, reqs(6), "t", pacer=pacer)
    assert failed == 3
    assert no_sleep.count(gather.COOLDOWN_S) == 1
    assert pacer.delay > gather.BASE_DELAY_S          # slowed down after throttling
    assert store.has("playbyplayv3", {"game_id": "g5"})


def test_isolated_failures_do_not_cool_down(tmp_path, monkeypatch, no_sleep):
    answers = iter([False, True, False, True, False, True])
    monkeypatch.setattr(gather, "fetch",
                        lambda req: {"ok": 1} if next(answers) else (_ for _ in ()).throw(RuntimeError("x")))
    gather.run(RawStore(tmp_path / "c.sqlite"), reqs(6), "t")
    assert gather.COOLDOWN_S not in no_sleep


def test_persistent_refusal_stops_instead_of_looping_forever(tmp_path, monkeypatch, no_sleep):
    monkeypatch.setattr(gather, "fetch", lambda req: (_ for _ in ()).throw(RuntimeError("empty")))
    with pytest.raises(gather.Throttled):
        gather.run(RawStore(tmp_path / "c.sqlite"), reqs(100), "t")
    assert no_sleep.count(gather.COOLDOWN_S) == gather.MAX_COOLDOWNS_WITHOUT_SUCCESS
