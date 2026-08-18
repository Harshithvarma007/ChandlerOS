"""Phase 2 definition-of-done check (Section 53):

"semantic and project-question golden slices pass; no regression on Phase
1's graph-only slice."

Covers the categories Phase 1 couldn't: semantic, project, blog, general.
Unlike eval_phase1.py this makes live embedding API calls (one per case,
paced to avoid the free-tier rate limit that build_chunks.py already hit
once) — retrieval-quality evaluation legitimately needs the real retrieval
path, not a mock.
"""
import json
import os
import sys
import time

from query_understanding import understand
from retrieval_router import GRAPH_PLUS_VECTOR, VECTOR_ONLY, decide_strategy
from vector_retrieval import retrieve_chunks

DATASET_PATH = os.path.join(os.path.dirname(__file__), "golden_dataset.json")
NEW_CATEGORIES = {"semantic", "project", "blog", "general"}
EMBED_PACING_SECONDS = 1.5


def run():
    with open(DATASET_PATH) as f:
        cases = json.load(f)

    cases = [c for c in cases if c.get("category") in NEW_CATEGORIES and not c.get("deferred_to_phase")]

    passed, failed = 0, []

    for case in cases:
        qu = understand(case["question"])
        strategy = decide_strategy(qu)
        reasons = []

        if qu.query_class != case["expected_query_class"]:
            reasons.append(f"query_class: expected {case['expected_query_class']}, got {qu.query_class}")

        if "expected_strategy" in case and strategy != case["expected_strategy"]:
            reasons.append(f"strategy: expected {case['expected_strategy']}, got {strategy}")

        if "expected_entities" in case:
            resolved_names = {e["canonical_name"] for e in qu.resolved_entities}
            missing = set(case["expected_entities"]) - resolved_names
            if missing:
                reasons.append(f"missing resolved entities: {missing}")

        if "expected_chunk_source_contains" in case and strategy in (VECTOR_ONLY, GRAPH_PLUS_VECTOR):
            resolved_ids = [e["id"] for e in qu.resolved_entities]
            chunks = retrieve_chunks(qu.raw_query, resolved_entity_ids=resolved_ids)
            time.sleep(EMBED_PACING_SECONDS)
            needle = case["expected_chunk_source_contains"]
            hit = any(needle in c.source_ref for c in chunks)
            if not hit:
                got = [c.source_ref for c in chunks[:3]]
                reasons.append(f"expected a chunk source_ref containing '{needle}', top results: {got}")

        if reasons:
            failed.append((case["id"], "; ".join(reasons)))
        else:
            passed += 1

    print(f"Phase 2 golden dataset (new categories): {passed}/{len(cases)} passed")
    if failed:
        print("\nFailures:")
        for case_id, reason in failed:
            print(f"  [{case_id}] {reason}")

    return len(failed) == 0


if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
