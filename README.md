# 07 - Cost-Aware Agent Router

> Pick the cheapest model that can actually do the job.

**What it demonstrates:** Controlling inference spend without silently degrading answers

**Status:** working implementation with passing tests. Built as a learning project to understand the pattern, not as a production service.

---

## Run it right now

No API key needed - every project ships with `MODEL=fake`, a deterministic
offline responder, so you can see the whole flow work before spending anything.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env               # Windows: copy .env.example .env
python -m src.main
pytest -q
```

To use a real model, edit `.env`:

```
MODEL=gpt-4o-mini            # + OPENAI_API_KEY
MODEL=claude-3-5-haiku-latest  # + ANTHROPIC_API_KEY
MODEL=ollama/llama3.1        # free, runs locally
```

## How it works

Tasks are classified into three tiers by a free heuristic - keyword patterns and length. Cost is projected *before* the call from published per-token prices, and if the projection exceeds the budget the router steps down one tier at a time rather than jumping straight to the cheapest model.

After the call, `self_confidence()` looks for hedging language. A hedged answer escalates one tier and retries, once - escalation is one-way, so it can't ping-pong. Every call is appended to `cost_ledger.jsonl`, and `report()` turns that into calls, total spend, cost-per-call and escalation rate.

## What "done" means here

- A free classifier picks the tier before any model is called
- Budget is enforced on the projection, not discovered from the invoice
- Over budget steps down one tier at a time
- A hedged answer escalates one tier, once, and the escalation is recorded
- Every call is written to a ledger with tier, cost and latency
- `report()` produces cost-per-decision from that ledger

Every one of those lines has a test behind it in `tests/` - `pytest -q` is the
proof, not the README.

## Layout

```
src/llm.py             provider-agnostic completion, plus offline fake mode
src/fake.py            the canned responses that make MODEL=fake work
src/logging_setup.py   structured JSON logging
src/agent.py           the pattern itself
src/main.py            CLI entrypoint
tests/                 12 tests, all passing
```

## Next steps

- Replace the keyword heuristic with a tiny classifier model and compare accuracy
- Benchmark 50 tasks routed vs always-frontier - record the cost delta AND the quality delta
- Add a semantic cache so repeated questions cost nothing
- Update `TIERS` prices from the providers' pricing pages before quoting any number

## Reference

https://docs.litellm.ai/docs/routing-load-balancing

---

Part of a 12-project agentic AI series - [github.com/dhanashalini25](https://github.com/dhanashalini25?tab=repositories)
