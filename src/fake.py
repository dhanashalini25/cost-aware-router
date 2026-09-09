"""Canned replies for MODEL=fake, including a hedged one to trigger escalation."""
from __future__ import annotations


def respond(messages: list[dict]) -> str:
    task = messages[-1]["content"].lower()
    if "compare" in task or "justify" in task:
        return (
            "For a write-heavy service, Postgres with partitioning handles the load with the "
            "fewest moving parts; Cassandra wins only past sustained six-figure writes per second."
        )
    if "?" in task and len(task) < 40:
        return "I'm not sure from what you've given me."
    return "Done."
