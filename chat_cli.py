"""Chat with ShopGuard in the terminal.

    python chat_cli.py            # uses a fresh copy of the store
    python chat_cli.py --rules off  # ablation: rules only in the prompt
"""
import argparse
import asyncio
import uuid

from shopguard.agent import Conversation
from shopguard.config import STORE_DB, TMP_DIR
from shopguard.db import fresh_copy
from shopguard.tracing import setup_tracing


async def main(rules: str) -> None:
    setup_tracing()
    if not STORE_DB.exists():
        from data.seed import seed

        seed()
    cid = uuid.uuid4().hex[:8]
    db = fresh_copy(STORE_DB, TMP_DIR / "cli" / f"{cid}.db")
    session = TMP_DIR / "cli" / f"{cid}.session.json"
    print("ShopGuard support. Try maya.lee@example.com, zip 94110. Type 'quit' to exit.\n")
    async with Conversation(db, session, rules_mode=rules) as convo:
        while True:
            msg = input("you> ").strip()
            if msg.lower() in ("quit", "exit"):
                break
            if not msg:
                continue
            turn = await convo.send(msg)
            for c in turn.tool_calls:
                print(f"   [tool] {c['tool']}({c['args']}) -> {(c['output'] or '')[:160]}")
            print(f"agent> {turn.reply}\n")
            if turn.escalated:
                print("(handed off to a human)")
                break
    print(f"Store copy for this chat: {db}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--rules", choices=["on", "off"], default="on")
    asyncio.run(main(p.parse_args().rules))
