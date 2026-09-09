"""Cost-Aware Agent Router - pick the cheapest model that can do the job.

Classifies the task, enforces a budget before the call rather than after,
escalates one tier when the cheap model is unsure, and writes every call to a
ledger so cost-per-decision is a number you can quote.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from .llm import complete
from .logging_setup import log

LEDGER = Path("cost_ledger.jsonl")
DEMO = "Compare three database options for a write-heavy service and justify a choice."

# USD per token, from published list prices - update these, don't trust them forever.
TIERS: dict[str, dict] = {
    "small":    {"model": "gpt-4o-mini",              "in": 0.15 / 1e6,  "out": 0.60 / 1e6},
    "mid":      {"model": "claude-3-5-haiku-latest",  "in": 0.80 / 1e6,  "out": 4.00 / 1e6},
    "frontier": {"model": "gpt-4o",                   "in": 2.50 / 1e6,  "out": 10.00 / 1e6},
}
ORDER = ["small", "mid", "frontier"]

DEFAULT_BUDGET_USD = 0.05
CONFIDENCE_FLOOR = 0.6
ASSUMED_OUTPUT_TOKENS = 600

HARD_WORDS = re.compile(
    r"\b(compare|justify|trade-?offs?|architect|design|prove|derive|why|strategy|migrate)\b",
    re.I,
)
EASY_WORDS = re.compile(r"\b(translate|capitalise|capitalize|list|format|spell|convert)\b", re.I)


@dataclass
class Result:
    text: str
    tier: str
    usd: float
    latency_ms: int
    escalated: bool = False
    trail: list[str] = field(default_factory=list)


def count_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def classify(task: str) -> str:
    """Heuristic first - it is free, instant, and right most of the time."""
    words = len(task.split())
    if EASY_WORDS.search(task) and words < 40:
        return "small"
    if HARD_WORDS.search(task) or words > 120:
        return "frontier"
    if words > 40:
        return "mid"
    return "small"


def estimate_usd(tier: str, in_tokens: int, out_tokens: int = ASSUMED_OUTPUT_TOKENS) -> float:
    t = TIERS[tier]
    return in_tokens * t["in"] + out_tokens * t["out"]


def downgrade(tier: str) -> str:
    i = ORDER.index(tier)
    return ORDER[max(i - 1, 0)]


def upgrade(tier: str) -> str:
    i = ORDER.index(tier)
    return ORDER[min(i + 1, len(ORDER) - 1)]


def fit_budget(tier: str, in_tokens: int, budget: float) -> str:
    """Step down one tier at a time until the projected cost fits."""
    while estimate_usd(tier, in_tokens) > budget and tier != ORDER[0]:
        cheaper = downgrade(tier)
        log.warning("budget_downgrade", extra={"from": tier, "to": cheaper, "budget": budget})
        tier = cheaper
    return tier


def self_confidence(text: str) -> float:
    """Cheap proxy: hedging language means the model is unsure."""
    hedges = ("i'm not sure", "i am not sure", "unclear", "cannot determine", "insufficient")
    lowered = text.lower()
    return 0.3 if any(h in lowered for h in hedges) else 0.9


def record(**fields) -> None:
    with LEDGER.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(fields, default=str) + "\n")


def route(task: str, budget_usd: float = DEFAULT_BUDGET_USD, *, allow_escalation: bool = True) -> Result:
    in_tokens = count_tokens(task)
    tier = fit_budget(classify(task), in_tokens, budget_usd)
    trail = [tier]

    started = time.perf_counter()
    text = complete([{"role": "user", "content": task}], model=TIERS[tier]["model"])
    spent = estimate_usd(tier, in_tokens, count_tokens(text))
    escalated = False

    if allow_escalation and self_confidence(text) < CONFIDENCE_FLOOR and tier != ORDER[-1]:
        better = upgrade(tier)
        if spent + estimate_usd(better, in_tokens) <= budget_usd * 2:
            log.info("escalating", extra={"from": tier, "to": better})
            text = complete([{"role": "user", "content": task}], model=TIERS[better]["model"])
            spent += estimate_usd(better, in_tokens, count_tokens(text))
            tier, escalated = better, True
            trail.append(better)

    latency = int((time.perf_counter() - started) * 1000)
    record(tier=tier, usd=round(spent, 6), ms=latency, escalated=escalated, task=task[:80])
    return Result(text=text, tier=tier, usd=spent, latency_ms=latency, escalated=escalated,
                  trail=trail)


def report(path: Path = LEDGER) -> dict:
    """Cost-per-decision over everything the ledger has seen."""
    if not path.exists():
        return {"calls": 0, "usd": 0.0, "usd_per_call": 0.0}
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    total = sum(r["usd"] for r in rows)
    return {
        "calls": len(rows),
        "usd": round(total, 6),
        "usd_per_call": round(total / len(rows), 6) if rows else 0.0,
        "escalation_rate": round(sum(r["escalated"] for r in rows) / len(rows), 3) if rows else 0.0,
    }


def run(prompt: str) -> str:
    r = route(prompt)
    tag = " -> ".join(r.trail)
    return f"[{tag} | ${r.usd:.6f} | {r.latency_ms}ms]\n{r.text}"
