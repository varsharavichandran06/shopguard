# ShopGuard

A retail customer support agent for a fake online store, and the eval system that measures how reliable it is.

The agent will handle returns, exchanges, cancellations and address changes. Every business rule lives in code, not in the prompt, so the model cannot be talked out of them.

## Status

Foundation only: the store database, the business rules and the order actions, with tests.

```
data/
  schema.sql      store tables (money in cents, fixed store clock)
  seed.py         builds store.db, same output every run
shopguard/
  rules.py        business rules as pure functions
  actions.py      order logic: verify, look up, return, exchange, cancel, change address
  config.py       settings
  db.py           SQLite helper
tests/            rule and action tests, no API key needed
```

## Run it

Python 3.11 or newer.

```bash
python -m venv .venv
.venv\Scripts\activate             # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m data.seed                # builds data/store.db
python -m pytest -q
```
