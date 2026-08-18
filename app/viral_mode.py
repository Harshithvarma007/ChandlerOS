"""Viral Mode — Section 36 of the blueprint.

    NORMAL -> BUSY -> HIGH_TRAFFIC -> VIRAL  (recovery: symmetric, hysteresis-gated)

Orthogonal to Graceful Degradation (Section 34): Viral Mode is about
*load*, Degradation is about *provider availability* — a system can be
simultaneously VIRAL and provider-healthy, or low-load and FALLBACK.

Transition logic requires sustained signal over an observation window in
BOTH directions (hysteresis) — prevents flapping on noisy minute-to-minute
traffic (Section 36).

Thresholds are illustrative defaults, not measured — this is a portfolio
site with no real production traffic history to derive a rolling 7-day
baseline from (Section 36's own suggested basis). Configurable, not
hardcoded in spirit even though there's no config file wired up for them
yet (would be the natural next step once real traffic data exists).
"""
import time
from collections import deque
from dataclasses import dataclass

NORMAL = "NORMAL"
BUSY = "BUSY"
HIGH_TRAFFIC = "HIGH_TRAFFIC"
VIRAL = "VIRAL"
_STATE_ORDER = [NORMAL, BUSY, HIGH_TRAFFIC, VIRAL]

OBSERVATION_WINDOW_S = 45  # Section 36: "30-60s" for transitions in both directions
REQUEST_WINDOW_S = 60  # rolling window requests/min is computed over

BASELINE_REQUESTS_PER_MIN = 5  # stand-in "normal" rate; a real deployment derives this from traffic history
BUSY_MULTIPLIER = 3
HIGH_TRAFFIC_MULTIPLIER = 10
VIRAL_MULTIPLIER = 30
HIGH_TRAFFIC_QUOTA_THRESHOLD = 0.7  # "any provider >70% of daily quota consumed"
VIRAL_QUOTA_THRESHOLD = 0.9


@dataclass
class ViralModeStatus:
    state: str
    requests_per_min: float
    reason: str


class ViralModeTracker:
    def __init__(self):
        self._request_timestamps = deque()
        self._committed_state = NORMAL

    def record_request(self, now: float = None):
        now = now if now is not None else time.monotonic()
        self._request_timestamps.append(now)
        cutoff = now - REQUEST_WINDOW_S
        while self._request_timestamps and self._request_timestamps[0] < cutoff:
            self._request_timestamps.popleft()

    def _requests_per_min_ending_at(self, end_time: float) -> float:
        window_start = end_time - REQUEST_WINDOW_S
        count = sum(1 for t in self._request_timestamps if window_start <= t <= end_time)
        return count * (60.0 / REQUEST_WINDOW_S)

    def _instantaneous_state(self, requests_per_min: float, quota_headroom_by_provider: dict) -> str:
        min_headroom = min(quota_headroom_by_provider.values()) if quota_headroom_by_provider else 1.0
        max_quota_used = 1.0 - min_headroom

        if requests_per_min > BASELINE_REQUESTS_PER_MIN * VIRAL_MULTIPLIER or max_quota_used > VIRAL_QUOTA_THRESHOLD:
            return VIRAL
        if requests_per_min > BASELINE_REQUESTS_PER_MIN * HIGH_TRAFFIC_MULTIPLIER or max_quota_used > HIGH_TRAFFIC_QUOTA_THRESHOLD:
            return HIGH_TRAFFIC
        if requests_per_min > BASELINE_REQUESTS_PER_MIN * BUSY_MULTIPLIER:
            return BUSY
        return NORMAL

    def compute_state(self, quota_headroom_by_provider: dict = None, now: float = None) -> ViralModeStatus:
        """Hysteresis (Section 36) is derived from the request-timestamp
        history itself — comparing the rate *now* against the rate a full
        OBSERVATION_WINDOW_S ago, both computed from the same stored data —
        rather than requiring compute_state() to be polled repeatedly
        across wall-clock time before it "notices" a sustained change. The
        polling-based approach would fail to ever escalate a burst that
        arrives right at startup (nothing to have polled yet) despite the
        data itself showing a clearly sustained spike, and would make the
        state machine untestable without literally sleeping through the
        observation window on every check.
        """
        now = now if now is not None else time.monotonic()
        quota_headroom_by_provider = quota_headroom_by_provider or {}

        rpm_now = self._requests_per_min_ending_at(now)
        rpm_window_ago = self._requests_per_min_ending_at(now - OBSERVATION_WINDOW_S)

        instantaneous = self._instantaneous_state(rpm_now, quota_headroom_by_provider)
        state_window_ago = self._instantaneous_state(rpm_window_ago, quota_headroom_by_provider)

        cur_idx = _STATE_ORDER.index(self._committed_state)
        inst_idx = _STATE_ORDER.index(instantaneous)
        ago_idx = _STATE_ORDER.index(state_window_ago)

        if inst_idx > cur_idx and ago_idx >= inst_idx:
            self._committed_state = instantaneous  # escalation sustained across the whole window
        elif inst_idx < cur_idx and ago_idx <= inst_idx:
            self._committed_state = instantaneous  # de-escalation sustained across the whole window

        return ViralModeStatus(
            state=self._committed_state,
            requests_per_min=rpm_now,
            reason=f"requests/min={rpm_now:.1f} (baseline={BASELINE_REQUESTS_PER_MIN}), instantaneous={instantaneous}, "
                   f"{OBSERVATION_WINDOW_S}s_ago={state_window_ago}, committed={self._committed_state}",
        )

    def reset(self):
        self._request_timestamps.clear()
        self._committed_state = NORMAL


_default_tracker = ViralModeTracker()


def get_viral_tracker() -> ViralModeTracker:
    return _default_tracker


# --- Effects (Section 36's response table, scoped subset) -----------------
#
# Implemented: rate-limit tightening, output token budget trimming, forcing
# chit-chat to the static blurb even with LLM capacity remaining (VIRAL
# only). NOT implemented, documented rather than silently skipped:
# semantic-cache threshold loosening and reranking/summary-regeneration
# skipping — there's no reranking or conversation-summary step in this
# pipeline yet for those to apply to.

RATE_LIMIT_TIGHTENING_FACTOR = {NORMAL: 1.0, BUSY: 0.8, HIGH_TRAFFIC: 0.5, VIRAL: 0.25}
OUTPUT_TOKEN_FACTOR = {NORMAL: 1.0, BUSY: 1.0, HIGH_TRAFFIC: 0.6, VIRAL: 0.4}


def rate_limit_tightening_factor(state: str) -> float:
    return RATE_LIMIT_TIGHTENING_FACTOR[state]


def max_output_tokens_for_state(state: str, base_max_tokens: int) -> int:
    return max(64, int(base_max_tokens * OUTPUT_TOKEN_FACTOR[state]))


def should_force_static_chitchat(state: str) -> bool:
    return state == VIRAL
