import json

import pytest

from src import agent
from src.agent import (
    ORDER, TIERS, classify, downgrade, estimate_usd, fit_budget, report, route, upgrade,
)


@pytest.fixture(autouse=True)
def ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "LEDGER", tmp_path / "ledger.jsonl")


def test_tiers_are_ordered_by_price():
    prices = [TIERS[t]["in"] for t in ORDER]
    assert prices == sorted(prices)


def test_classify_easy_task():
    assert classify("Translate 'good morning' to Tamil") == "small"


def test_classify_hard_task():
    assert classify("Compare three databases and justify the trade-offs") == "frontier"


def test_classify_medium_task():
    assert classify(" ".join(["word"] * 60)) == "mid"


def test_estimate_scales_with_tier():
    assert estimate_usd("small", 1000) < estimate_usd("frontier", 1000)


def test_downgrade_and_upgrade_are_bounded():
    assert downgrade("small") == "small"
    assert upgrade("frontier") == "frontier"
    assert upgrade("small") == "mid"


def test_budget_forces_downgrade():
    assert fit_budget("frontier", 1000, budget=0.0001) == "small"


def test_generous_budget_keeps_tier():
    assert fit_budget("frontier", 1000, budget=10.0) == "frontier"


def test_route_records_to_ledger(monkeypatch):
    monkeypatch.setattr(agent, "complete", lambda m, model=None, **k: "A confident answer.")
    route("Translate hello to Tamil")
    rows = agent.LEDGER.read_text(encoding="utf-8").strip().splitlines()
    assert json.loads(rows[0])["tier"] == "small"


def test_hedged_answer_escalates(monkeypatch):
    calls = []

    def hedge_then_confident(messages, model=None, **kwargs):
        calls.append(model)
        return "I'm not sure." if len(calls) == 1 else "Definitely Postgres."

    monkeypatch.setattr(agent, "complete", hedge_then_confident)
    r = route("List the options")
    assert r.escalated and len(r.trail) == 2


def test_escalation_can_be_disabled(monkeypatch):
    monkeypatch.setattr(agent, "complete", lambda m, model=None, **k: "I'm not sure.")
    assert not route("List the options", allow_escalation=False).escalated


def test_report_computes_cost_per_call(monkeypatch):
    monkeypatch.setattr(agent, "complete", lambda m, model=None, **k: "Fine.")
    route("Translate hello")
    route("Translate goodbye")
    rep = report(agent.LEDGER)
    assert rep["calls"] == 2 and rep["usd_per_call"] > 0
