# ShopGuard

A retail customer support agent for a fake online store, and the eval system that measures how reliable it is.

The agent handles returns, exchanges, cancellations and address changes. Every business rule lives in code, not in the prompt, so the model cannot be talked out of them.

## Status

A basic working chatbot: it verifies a customer, looks up orders and handles returns, exchanges, cancellations and address changes through MCP tools.

```
data/
  schema.sql      store tables (money in cents, fixed store clock)
  seed.py         builds store.db, same output every run
shopguard/
  rules.py        business rules as pure functions
  actions.py      order logic: verify, look up, return, exchange, cancel, change address
  mcp_server.py   MCP server exposing 8 order tools (official MCP Python SDK)
  prompts.py      short behavior prompt (rules are not in here)
  agent.py        OpenAI Agents SDK agent and a Conversation wrapper
  config.py       settings
  db.py           SQLite helper
chat_cli.py       terminal chat
tests/            rule, action and end-to-end tests, no API key needed
```

## Run it

Python 3.11 or newer.

```bash
python -m venv .venv
.venv\Scripts\activate             # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env               # then paste your OPENAI_API_KEY into .env
python -m data.seed                # builds data/store.db
python -m pytest -q                # free, no key needed
python chat_cli.py                 # chat in the terminal
```

Demo customers (verify with email and zip):

| Customer | Email | Zip | Good for |
| --- | --- | --- | --- |
| Maya Lee | maya.lee@example.com | 94110 | W1043 returnable, W1042 too late |
| Omar Haddad | omar.h@example.com | 10027 | W1050 cancel, W1051 shipped |
| Priya Nair | priya.nair@example.com | 60614 | W1060 has a final sale item |
| Dan Brooks | dan.brooks@example.com | 98103 | address change, tee exchange |
| Lena Park | lena.park@example.com | 30307 | return on exactly day 30 |
| Sam Ortiz | sam.ortiz@example.com | 02139 | damaged $249 item |

## Try the MCP server

```bash
python -m shopguard.mcp_server                                       # speaks MCP over stdio
npx @modelcontextprotocol/inspector python -m shopguard.mcp_server   # poke the tools by hand
```

The server reads `DB_PATH` (which store copy to use) and `SESSION_PATH` (a small JSON file holding the verified customer). All rules are enforced inside the tools.
