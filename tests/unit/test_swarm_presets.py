import pytest

from aletheia.core.swarm.presets import (
    available_presets,
    get_investment_team,
    get_preset,
    register_preset,
)
from aletheia.core.swarm.worker import SwarmWorker


def test_builtin_presets_are_registered() -> None:
    presets = available_presets()
    assert "investment_team" in presets
    assert "due_diligence_team" in presets


def test_get_preset_returns_real_workers() -> None:
    workers = get_preset("investment_team")
    assert workers
    assert all(isinstance(w, SwarmWorker) for w in workers)
    # Fresh instances each call — no shared LLM/tool state across requests.
    assert [w.name for w in workers] == [w.name for w in get_investment_team()]
    assert workers[0] is not get_investment_team()[0]


def test_get_preset_unknown_name_raises_with_available_list() -> None:
    with pytest.raises(ValueError, match="investment_team"):
        get_preset("does_not_exist")


def test_register_preset_adds_a_custom_team() -> None:
    def _fake_team():
        return []

    register_preset("empty_team", _fake_team)
    try:
        assert "empty_team" in available_presets()
        assert get_preset("empty_team") == []
    finally:
        from aletheia.core.swarm.presets import _PRESET_REGISTRY

        _PRESET_REGISTRY.pop("empty_team", None)


@pytest.mark.parametrize("name", ["quant_team", "crypto_team", "macro_team", "smallcap_team"])
def test_specialist_presets_are_distinct_and_use_real_tools(name: str) -> None:
    from aletheia.core.tools.registry import _discover_subclasses

    known = {cls.name for cls in _discover_subclasses()}
    workers = get_preset(name)
    assert workers and all(isinstance(w, SwarmWorker) for w in workers)
    for w in workers:
        assert set(w.allowed_tools) <= known, (name, w.name, set(w.allowed_tools) - known)


def test_specialist_teams_differ_from_each_other() -> None:
    descriptions = {
        n: " ".join(w.role_description for w in get_preset(n))
        for n in ("crypto_team", "macro_team", "smallcap_team", "quant_team")
    }
    assert len(set(descriptions.values())) == 4
    assert "VDA" in descriptions["crypto_team"]
    assert "promoter" in descriptions["smallcap_team"]
