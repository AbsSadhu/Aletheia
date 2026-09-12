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


def test_evaluate_against_backtest_validates_on_high_sharpe(registry: HypothesisRegistry) -> None:
    hypo = registry.propose(title="t", description="d", test_criteria="c")
    result = registry.evaluate_against_backtest(hypo.id, sharpe_ratio=1.8, threshold=1.0)

    assert result.status == "validated"
    assert result.evidence
    assert result.evidence[-1].supports_hypothesis is True


def test_evaluate_against_backtest_rejects_on_low_sharpe(registry: HypothesisRegistry) -> None:
    hypo = registry.propose(title="t", description="d", test_criteria="c")
    result = registry.evaluate_against_backtest(hypo.id, sharpe_ratio=0.2, threshold=1.0)

    assert result.status == "rejected"
    assert result.evidence[-1].supports_hypothesis is False


def test_evaluate_against_backtest_moves_proposed_through_testing_first(
    registry: HypothesisRegistry,
) -> None:
    hypo = registry.propose(title="t", description="d", test_criteria="c")
    assert hypo.status == "proposed"

    result = registry.evaluate_against_backtest(hypo.id, sharpe_ratio=2.0, threshold=1.0)
    assert result.status == "validated"  # passed through "testing", not stuck there


def test_evaluate_against_backtest_does_not_flip_an_already_validated_hypothesis(
    registry: HypothesisRegistry,
) -> None:
    hypo = registry.propose(title="t", description="d", test_criteria="c")
    registry.evaluate_against_backtest(hypo.id, sharpe_ratio=2.0, threshold=1.0)
    assert registry.get(hypo.id).status == "validated"

    # A later re-link with a bad Sharpe must not silently overwrite it.
    result = registry.evaluate_against_backtest(hypo.id, sharpe_ratio=0.1, threshold=1.0)
    assert result.status == "validated"


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
