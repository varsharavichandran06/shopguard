# ShopGuard

A retail customer support agent for a fake online store, and the eval system that measures how reliable it is.

The agent handles returns, exchanges, cancellations and address changes. Every business rule lives in code, not in the prompt, so the model cannot be talked out of them.

## Status

A working support chatbot. It verifies a customer, handles returns, exchanges, cancellations and address changes through MCP tools, answers policy questions with citations, blocks card numbers and prompt injection, and hands hard cases to a human.

```
data/
  schema.sql      store tables (money in cents, fixed store clock)
  seed.py         builds store.db, same output every run
  policy/*.md     store policy docs the agent searches
  policy/*.md     store policy docs the agent searches
shopguard/
  rules.py        business rules as pure functions
  actions.py      order logic: verify, look up, return, exchange, cancel, change address
  mcp_server.py   MCP server exposing 8 order tools (official MCP Python SDK)
  search.py       BM25 + embeddings, fused with RRF, relevance floor, citations
  guardrails.py   input guardrail: card numbers and prompt injection
  prompts.py      short behavior prompt (rules are not in here)
  agent.py        OpenAI Agents SDK agent, human handoff, Conversation wrapper
  tracing.py      traces to the OpenAI dashboard, optional Langfuse
  config.py       settings
  db.py           SQLite helper
app.py            Streamlit chat UI with a live store view
chat_cli.py       terminal chat
tests/            rule, action, search and end-to-end tests, no API key needed
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
streamlit run app.py               # chat UI at http://localhost:8501
python chat_cli.py                 # or chat in the terminal
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

## Deploy

### Option 1: Streamlit Community Cloud (free)

1. Push this repo to GitHub.
2. Go to share.streamlit.io, click New app, pick the repo and `app.py`.
3. In Advanced settings, Secrets, add `OPENAI_API_KEY = "sk-..."`. Add `APP_PASSWORD = "..."` if you want a password gate.
4. Deploy. The app builds the store on first start.

### Option 2: Docker or Google Cloud Run

```bash
docker build -t shopguard .
docker run --rm -p 8501:8501 --env-file .env shopguard
```

```bash
gcloud run deploy shopguard --source . --region us-central1 --allow-unauthenticated \
  --set-env-vars OPENAI_API_KEY=sk-...,DAILY_TURN_BUDGET=200 --memory 1Gi
```

For a real deploy, store the key in Secret Manager instead of a plain env var.

The public app has a per chat turn limit, a daily turn budget and a 2000 character input cap, so strangers cannot run up your OpenAI bill. Also set a monthly limit in your OpenAI account.

## Tracing

By default the OpenAI Agents SDK sends a trace of every run (each model call, tool call, handoff and guardrail) to the Traces page of your OpenAI dashboard. Nothing to set up.

Optional: send the same traces to Langfuse.

```bash
pip install -r requirements-tracing.txt
# set LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST in .env
```
