# ShopGuard

A retail customer support agent for a fake online store, and the eval system that measures how reliable it is.

The agent will handle returns, exchanges, cancellations and address changes. Every business rule lives in code, not in the prompt, so the model cannot be talked out of them.

## Status

Store database, business rules, order actions and an MCP server that exposes them as tools.

```
data/
  schema.sql      store tables (money in cents, fixed store clock)
  seed.py         builds store.db, same output every run
shopguard/
  rules.py        business rules as pure functions
  actions.py      order logic: verify, look up, return, exchange, cancel, change address
  mcp_server.py   MCP server exposing 8 order tools (official MCP Python SDK)
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

## Try the MCP server

```bash
python -m shopguard.mcp_server                                   # speaks MCP over stdio
npx @modelcontextprotocol/inspector python -m shopguard.mcp_server   # poke the tools by hand
```

The server reads `DB_PATH` (which store copy to use) and `SESSION_PATH` (a small JSON file holding the verified customer). All rules are enforced inside the tools.
