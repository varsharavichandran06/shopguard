"""End to end with no API key.

The agent's model is the SDK's ScriptedModel, so model replies are fixed, but everything else
is real: the MCP server subprocess, the tools and rules, the guardrail and the session file.
"""
import asyncio

from agents.testing import ModelStep, ScriptedModel, assistant_message, function_call

from shopguard.agent import Conversation
from shopguard.db import fresh_copy, open_db

MAYA = {"email": "maya.lee@example.com", "zip": "94110"}


def scripted_return(order_id, item_id, method):
    return ScriptedModel([
        ModelStep(output=[function_call("verify_user", MAYA, call_id="c1")]),
        ModelStep(output=[assistant_message("Thanks Maya, you're verified. Return the jacket from W1043 for store credit?")]),
        ModelStep(output=[function_call("return_items", {"order_id": order_id, "item_ids": [item_id], "refund_method": method}, call_id="c2")]),
        ModelStep(output=[assistant_message("Done. Your return is processed.")]),
    ])


def test_conversation_over_real_mcp(tmp_path, seeded_store):
    db = fresh_copy(seeded_store, tmp_path / "s.db")
    session = tmp_path / "s.json"
    model = scripted_return("W1043", "W1043-1", "store_credit")

    async def go():
        async with Conversation(db, session, model=model) as c:
            t1 = await c.send("hi, maya.lee@example.com, 94110")
        # new MCP process for turn 2: identity survives in the session file
        async with Conversation(db, session, history=c.history, model=model) as c2:
            t2 = await c2.send("yes please")
            t3 = await c2.send("here is my card 4242 4242 4242 4242")
        return t1, t2, t3

    t1, t2, t3 = asyncio.run(go())
    assert t1.tool_calls[0]["tool"] == "verify_user" and "U1001" in t1.tool_calls[0]["output"]
    assert t2.tool_calls[0]["tool"] == "return_items" and "8900" in t2.tool_calls[0]["output"]
    assert t3.guardrail == "card_number"
    rows = open_db(db).execute("SELECT item_id, refund_method FROM returns").fetchall()
    assert [tuple(r) for r in rows] == [("W1043-1", "store_credit")]


def test_rules_block_inside_the_tool(tmp_path, seeded_store):
    db = fresh_copy(seeded_store, tmp_path / "s.db")
    model = ScriptedModel([
        ModelStep(output=[function_call("verify_user", MAYA, call_id="c1")]),
        ModelStep(output=[function_call("return_items", {"order_id": "W1042", "item_ids": ["W1042-1"], "refund_method": "original_payment"}, call_id="c2")]),
        ModelStep(output=[assistant_message("Sorry, that is past the 30 day window.")]),
    ])

    async def go():
        async with Conversation(db, tmp_path / "s.json", model=model) as c:
            return await c.send("refund W1042 now")

    t = asyncio.run(go())
    assert "window" in t.tool_calls[1]["output"]
    assert open_db(db).execute("SELECT COUNT(*) FROM returns").fetchone()[0] == 0
