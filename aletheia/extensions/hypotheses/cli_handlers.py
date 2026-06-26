from aletheia.extensions.hypotheses.registry import HypothesisRegistry
from aletheia.extensions.hypotheses.models import Evidence


def propose_hypothesis(args):
    registry = HypothesisRegistry()
    hypo = registry.propose(
        title=args.title, description=args.description, test_criteria=args.criteria
    )
    print(f"Hypothesis '{hypo.title}' proposed successfully. ID: {hypo.id}")


def list_hypotheses(args):
    registry = HypothesisRegistry()
    hypos = registry.list_all(status=args.status)
    if not hypos:
        print("No hypotheses found.")
        return
    for h in hypos:
        print(f"[{h.id}] {h.title} (Status: {h.status}) - {len(h.evidence)} evidence items")


def add_evidence(args):
    registry = HypothesisRegistry()
    hypo = registry.get(args.id)
    if not hypo:
        print(f"Hypothesis {args.id} not found.")
        return

    ev = Evidence(source=args.source, description=args.desc, supports_hypothesis=not args.refutes)
    hypo.add_evidence(ev)
    registry.save(hypo)
    print(f"Evidence added to Hypothesis {hypo.id}.")


def update_status(args):
    registry = HypothesisRegistry()
    hypo = registry.get(args.id)
    if not hypo:
        print(f"Hypothesis {args.id} not found.")
        return

    hypo.status = args.status
    registry.save(hypo)
    print(f"Hypothesis {hypo.id} status updated to {args.status}.")
