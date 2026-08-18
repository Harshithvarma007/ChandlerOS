"""Phase 1 definition-of-done check (Section 53):

"correctly answers the golden dataset's simple/relationship/multi-hop slice,
refuses on the unknown slice."

This checks the deterministic layers only (query understanding + graph
retrieval) — no LLM calls, no LLM-as-a-judge (that's Phase 10). For this
phase, "correct" means: the right entities were resolved and retrieved, and
unknown questions hit the refusal path. Whether the generated *prose* is
good is a judgment call the LLM call in ask.py handles; grading that
automatically comes later.
"""
import json
import os
import sys

from graph_retrieval import retrieve_subgraph
from query_understanding import understand

DATASET_PATH = os.path.join(os.path.dirname(__file__), "golden_dataset.json")
PHASE1_CATEGORIES = {"simple_fact", "entity_lookup", "relationship", "multi_hop", "unknown"}


def run():
    with open(DATASET_PATH) as f:
        cases = json.load(f)

    passed, failed = 0, []
    active_cases = [
        c for c in cases if not c.get("deferred_to_phase") and c.get("category") in PHASE1_CATEGORIES
    ]

    for case in active_cases:

        qu = understand(case["question"])

        if case.get("expected_refusal"):
            ok = qu.query_class == "unknown" or not qu.resolved_entities
            if ok:
                passed += 1
            else:
                failed.append((case["id"], f"expected refusal, got query_class={qu.query_class}, "
                                            f"entities={[e['canonical_name'] for e in qu.resolved_entities]}"))
            continue

        class_ok = qu.query_class == case["expected_query_class"]
        subgraph = retrieve_subgraph(qu)
        retrieved_names = set()
        for fact in subgraph.facts:
            retrieved_names.add(fact.source["canonical_name"])
            retrieved_names.add(fact.target["canonical_name"])

        expected = set(case["expected_entities"])
        entities_ok = expected.issubset(retrieved_names)

        if class_ok and entities_ok:
            passed += 1
        else:
            reasons = []
            if not class_ok:
                reasons.append(f"query_class: expected {case['expected_query_class']}, got {qu.query_class}")
            if not entities_ok:
                reasons.append(f"missing entities: {expected - retrieved_names}; retrieved: {retrieved_names}")
            failed.append((case["id"], "; ".join(reasons)))

    print(f"Phase 1 golden dataset (simple/entity_lookup/relationship/multi_hop/unknown slice): "
          f"{passed}/{len(active_cases)} passed")
    if failed:
        print("\nFailures:")
        for case_id, reason in failed:
            print(f"  [{case_id}] {reason}")

    return len(failed) == 0


if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
