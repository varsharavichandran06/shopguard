"""MCP server that exposes the store as tools. Rules are enforced inside the tools.

Run by hand:   python -m shopguard.mcp_server
Inspector:     npx @modelcontextprotocol/inspector python -m shopguard.mcp_server

Env:
  DB_PATH       which store.db copy to use
  SESSION_PATH  JSON file holding the verified user (lets the server restart per turn)

Never print to stdout here. stdout is the protocol channel. Use stderr.
"""
import json
import os
import sys
from typing import Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError as MCPToolError

from . import actions as A
from .config import STORE_DB
from .db import open_db

VERSION = "1.0.0"

server = MCPServer(name="shopguard-orders", version=VERSION)


def _call(fn, *args, **kwargs) -> str:
    """Open the DB, load the session, run the action, return JSON text.
    Business errors come back as tool errors the model can read."""
    conn = open_db(os.environ.get("DB_PATH", STORE_DB))
    session = A.Session.load(os.environ.get("SESSION_PATH"))
    try:
        return json.dumps(fn(conn, session, *args, **kwargs))
    except A.ToolError as e:
        raise MCPToolError(str(e)) from e
    except Exception as e:  # unexpected bug: log to stderr, give the model a safe next step
        print(f"internal error: {e!r}", file=sys.stderr)
        raise MCPToolError("Internal error. Apologize and hand off to a human.") from e
    finally:
        conn.close()


@server.tool(description="Verify the customer by email and zip code. Must succeed before any order tool.")
def verify_user(email: str, zip: str) -> str:
    return _call(A.verify_user, email, zip)


@server.tool(description="List the verified customer's orders, newest first.")
def get_user_orders() -> str:
    return _call(A.get_user_orders)


@server.tool(description="Get one order with its items, item ids, prices, final sale flags and days since delivery.")
def get_order(order_id: str) -> str:
    return _call(A.get_order, order_id)


@server.tool(description="Get a product and its variants (size, color, stock). Use before an exchange.")
def get_product(product_id: str) -> str:
    return _call(lambda conn, s, pid: A.get_product(conn, pid), product_id)


@server.tool(
    description=(
        "Return delivered items for a refund. Only call after you read back the items and the refund "
        "method and the customer clearly says yes. refund_method is original_payment or store_credit."
    )
)
def return_items(order_id: str, item_ids: list[str], refund_method: Literal["original_payment", "store_credit"]) -> str:
    return _call(A.return_items, order_id, item_ids, refund_method)


@server.tool(description="Exchange one item for another size or color of the same product. Only call after the customer confirms.")
def exchange_item(order_id: str, item_id: str, new_variant_id: str) -> str:
    return _call(A.exchange_item, order_id, item_id, new_variant_id)


@server.tool(description="Cancel a pending order. Only call after the customer confirms.")
def cancel_order(order_id: str, reason: str) -> str:
    return _call(A.cancel_order, order_id, reason)


@server.tool(
    description="Change the shipping address of an order that has not shipped. Only call after the customer confirms the full new address."
)
def change_address(order_id: str, new_address: str) -> str:
    return _call(A.change_address, order_id, new_address)


if __name__ == "__main__":
    print(f"shopguard-orders MCP server {VERSION} on stdio", file=sys.stderr)
    server.run("stdio")
