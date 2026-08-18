"""Timeout Strategy — Section 22 of the blueprint.

Total request budget is hard-capped; per-stage budgets are soft (a fast
stage can donate unused time to a slower one, logged when a stage overruns
its own soft budget so it's visible which stage is actually slow) but every
stage can check the shared deadline and shrink its own behavior once budget
is tight.

If the deadline is exhausted before generation completes, the caller should
short-circuit rather than let the request hang — full Graceful Degradation
(Section 34) is Phase 8; here that just means returning an honest "ran out
of time" response instead of blocking indefinitely.
"""
import time

TOTAL_BUDGET_MS = 6000

# Soft, informational budgets (Section 22's table) — logged when exceeded,
# never force-killed mid-stage at this scale (killing a SQLite query
# mid-flight isn't practical or necessary locally; enforcement matters most
# for the LLM call, which the Gateway's retry loop already deadline-caps).
STAGE_SOFT_BUDGETS_MS = {
    "abuse_and_rate_limit": 20,
    "query_understanding": 30,
    "graph_retrieval": 150,
    "vector_retrieval": 200,
    "context_building": 30,
    "output_validation": 100,
    "response_assembly": 20,
}

MIN_BUDGET_FOR_LLM_CALL_MS = 500  # below this, don't even attempt generation


class RequestBudget:
    def __init__(self, total_ms=TOTAL_BUDGET_MS):
        self.total_ms = total_ms
        self._start = time.monotonic()
        self.stage_timings_ms = {}

    def elapsed_ms(self) -> float:
        return (time.monotonic() - self._start) * 1000

    def remaining_ms(self) -> float:
        return max(0.0, self.total_ms - self.elapsed_ms())

    def exceeded(self) -> bool:
        return self.remaining_ms() <= 0

    def stage(self, name: str):
        return _StageTimer(self, name)


class _StageTimer:
    def __init__(self, budget: RequestBudget, name: str):
        self.budget = budget
        self.name = name
        self._t0 = None

    def __enter__(self):
        self._t0 = time.monotonic()
        return self

    def __exit__(self, *exc_info):
        elapsed_ms = (time.monotonic() - self._t0) * 1000
        self.budget.stage_timings_ms[self.name] = elapsed_ms
        soft_budget = STAGE_SOFT_BUDGETS_MS.get(self.name)
        if soft_budget is not None and elapsed_ms > soft_budget:
            print(f"[budget] stage '{self.name}' took {elapsed_ms:.0f}ms "
                  f"(soft budget {soft_budget}ms) — {self.budget.remaining_ms():.0f}ms left overall")
        return False
