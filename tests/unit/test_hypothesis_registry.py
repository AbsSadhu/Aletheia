import pytest

from aletheia.extensions.hypotheses.registry import HypothesisRegistry


@pytest.fixture
def registry(tmp_path) -> HypothesisRegistry:
    return HypothesisRegistry(db_path=str(tmp_path / "hypotheses.db"))


def test_propose_creates_hypothesis_with_no_backtest_link(registry: HypothesisRegistry) -> None:
    hypo = registry.propose(title="t", description="d", test_criteria="c")
    assert hypo.status == "proposed"
    assert hypo.backtest_run_id is None


def test_link_to_backtest_persists_and_is_readable_via_get(registry: HypothesisRegistry) -> None:
    hypo = registry.propose(title="t", description="d", test_criteria="c")
    linked = registry.link_to_backtest(hypo.id, "run-123")
    assert linked.backtest_run_id == "run-123"

    fetched = registry.get(hypo.id)
    assert fetched is not None
    assert fetched.backtest_run_id == "run-123"


def test_backtest_link_survives_a_later_transition(registry: HypothesisRegistry) -> None:
    """Regression test: save() used to omit backtest_run_id from its column
    list, so any later save() (e.g. via transition()) silently wiped the
    link back to NULL."""
    hypo = registry.propose(title="t", description="d", test_criteria="c")
    registry.link_to_backtest(hypo.id, "run-123")

    transitioned = registry.transition(hypo.id, "testing")
    assert transitioned.backtest_run_id == "run-123"

    fetched = registry.get(hypo.id)
    assert fetched is not None
    assert fetched.backtest_run_id == "run-123"


def test_backtest_link_survives_in_list_all(registry: HypothesisRegistry) -> None:
    hypo = registry.propose(title="t", description="d", test_criteria="c")
    registry.link_to_backtest(hypo.id, "run-123")

    results = registry.list_all()
    assert len(results) == 1
    assert results[0].backtest_run_id == "run-123"


def test_add_evidence_does_not_raise_and_persists(registry: HypothesisRegistry) -> None:
    """Regression test: add_evidence() used to construct Evidence with
    summary=/supports= kwargs that don't exist on the model
    (description=/supports_hypothesis= are the real fields), so this call
    raised a pydantic ValidationError for every request."""
    hypo = registry.propose(title="t", description="d", test_criteria="c")

    updated = registry.add_evidence(
        hypo.id, source="paper", summary="strong backtest result", supports=True
    )

    assert len(updated.evidence) == 1
    ev = updated.evidence[0]
    assert ev.source == "paper"
    assert ev.description == "strong backtest result"
    assert ev.supports_hypothesis is True

    fetched = registry.get(hypo.id)
    assert fetched is not None
    assert len(fetched.evidence) == 1
    assert fetched.evidence[0].description == "strong backtest result"


def test_add_evidence_preserves_backtest_link(registry: HypothesisRegistry) -> None:
    hypo = registry.propose(title="t", description="d", test_criteria="c")
    registry.link_to_backtest(hypo.id, "run-123")

    updated = registry.add_evidence(hypo.id, source="paper", summary="x", supports=False)

    assert updated.backtest_run_id == "run-123"
