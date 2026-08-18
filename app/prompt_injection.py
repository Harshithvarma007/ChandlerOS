"""Prompt Injection Defense — Section 30 of the blueprint.

Detection scope is deliberately USER INPUT only, not retrieved knowledge:
knowledge is curated/reviewed at ingestion time (Section "Knowledge
Ingestion") and is lower-risk, though the ingestion pipeline itself should
screen scraped sources (READMEs etc.) separately — that screening is not
this module's job.

This is a heuristic pre-generation scan, not a hard block: flagged requests
still get answered, but with a tightened personality (near-zero humor/
flourish — see personality_policy.py's injection_flagged override) and are
logged distinctly, matching Section 30: "flagged requests get a tightened
personality/lower creative-freedom prompt variant and are logged distinctly,
not silently allowed through." The real backstop against actual behavior
change is structural: the fenced delimiters + instruction hierarchy in
prompt.py, and Output Validation (Section 31) catching anything that leaks
through anyway.
"""
import re
from dataclasses import dataclass, field

INJECTION_PATTERNS = [
    (r"\bignore (all |the )?(previous|prior|above|earlier) instructions\b", "ignore_instructions"),
    (r"\bdisregard (all |the )?(previous|prior|your) instructions\b", "disregard_instructions"),
    (r"\byou are now\b", "role_reassignment"),
    (r"\bact as (a|an)?\b", "role_reassignment"),
    (r"\bnew instructions?:", "fake_instruction_block"),
    (r"\bsystem\s*:", "fake_role_marker"),
    (r"\bassistant\s*:", "fake_role_marker"),
    (r"\breveal (your |the )?(system )?prompt\b", "prompt_extraction"),
    (r"\bwhat (is|are) your (system )?instructions?\b", "prompt_extraction"),
    (r"===\s*(begin|end)[_ ]", "delimiter_mimicry"),
    (r"\btrusted_knowledge\s*:", "delimiter_mimicry"),
    (r"\bsystem_instructions\s*:", "delimiter_mimicry"),
]


@dataclass
class InjectionCheckResult:
    flagged: bool
    matched: list = field(default_factory=list)  # list of pattern tags


def check_injection(raw_query: str) -> InjectionCheckResult:
    if not raw_query:
        return InjectionCheckResult(flagged=False)
    text = raw_query.lower()
    matched = [tag for pattern, tag in INJECTION_PATTERNS if re.search(pattern, text)]
    return InjectionCheckResult(flagged=bool(matched), matched=matched)
