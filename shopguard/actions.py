"""The real order logic. The MCP server is a thin wrapper around these functions.

The grader calls these same functions directly (no LLM) to build the expected end
state, so the agent and the grader always run the exact same code.
"""
import json
import os
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from . import rules


class ToolError(Exception):
    """A business or validation error the model should read and act on."""


@dataclass
class Session:
    """Who is verified in this conversation. Optionally persisted to a JSON file,
    so the MCP server can be restarted per turn without losing identity."""

    user_id: str | None = None
    path: Path | None = field(default=None, repr=False)

    @classmethod
    def load(cls, path: str | Path | None) -> "Session":
        if not path:
            return cls()
        p = Path(path)
        if p.exists():
            return cls(user_id=json.loads(p.read_text()).get("user_id"), path=p)
        return cls(path=p)

    def save(self) -> None:
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps({"user_id": self.user_id}))


def _enforce(check: rules.Check) -> None:
    """Raise if a rule fails. SHOPGUARD_RULES=off turns rules off for the ablation run only."""
    ok, reason = check
    if not ok and os.environ.get("SHOPGUARD_RULES", "on") != "off":
        raise ToolError(reason)


def _row(conn: sqlite3.Connection, sql: str, *args) -> dict | None:
    r = conn.execute(sql, args).fetchone()
    return dict(r) if r else None


def get_today(conn) -> str:
    return _row(conn, "SELECT value FROM store_config WHERE key = 'store_today'")["value"]


def _require_user(s: Session) -> str:
    if not s.user_id:
        raise ToolError("Verify the customer first with verify_user (email and zip).")
    return s.user_id


def _load_order(conn, s: Session, order_id: str) -> dict:
    user_id = _require_user(s)
    order = _row(conn, "SELECT * FROM orders WHERE id = ?", order_id.strip().upper())
    # Same message for "missing" and "not yours": never reveal that another customer's order exists.
    if not order or order["user_id"] != user_id:
        raise ToolError(f"No order {order_id} found for this customer. Use get_user_orders to list their orders.")
    return order


def _load_item(conn, order: dict, item_id: str) -> dict:
    item = _row(conn, "SELECT * FROM order_items WHERE id = ? AND order_id = ?", item_id.strip().upper(), order["id"])
    if not item:
        raise ToolError(f"Item {item_id} is not in order {order['id']}. Use get_order to see item ids.")
    return item


def _variant(conn, vid: str) -> dict | None:
    return _row(conn, "SELECT * FROM variants WHERE id = ?", vid.strip().upper())


def _product(conn, pid: str) -> dict:
    return _row(conn, "SELECT * FROM products WHERE id = ?", pid)


def _log(conn, order_id: str, event: str, detail: str) -> None:
    conn.execute("INSERT INTO order_events (order_id, event, detail) VALUES (?,?,?)", (order_id, event, detail))


# ---------------- read tools ----------------

def verify_user(conn, s: Session, email: str, zip: str) -> dict:
    user = _row(
        conn,
        "SELECT * FROM users WHERE lower(email) = lower(?) AND zip = ?",
        email.strip(), zip.strip(),
    )
    if not user:
        raise ToolError("No customer matches that email and zip. Ask the customer to check both.")
    s.user_id = user["id"]
    s.save()
    return {"verified": True, "user_id": user["id"], "name": user["name"]}


def get_user_orders(conn, s: Session) -> list[dict]:
    uid = _require_user(s)
    rows = conn.execute(
        """SELECT o.id, o.status, o.placed_at, o.delivered_at, COUNT(i.id) AS items
           FROM orders o JOIN order_items i ON i.order_id = o.id
           WHERE o.user_id = ? GROUP BY o.id ORDER BY o.placed_at DESC""",
        (uid,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_order(conn, s: Session, order_id: str) -> dict:
    order = _load_order(conn, s, order_id)
    items = conn.execute(
        """SELECT i.id AS item_id, i.status, i.price_cents, v.id AS variant_id, v.size, v.color,
                  p.id AS product_id, p.name, p.final_sale
           FROM order_items i JOIN variants v ON v.id = i.variant_id JOIN products p ON p.id = v.product_id
           WHERE i.order_id = ? ORDER BY i.id""",
        (order["id"],),
    ).fetchall()
    out = {k: v for k, v in order.items() if k != "user_id"}
    out["items"] = [dict(r) for r in items]
    out["store_today"] = get_today(conn)
    if order["delivered_at"]:
        out["days_since_delivery"] = rules.days_since(order["delivered_at"], out["store_today"])
    return out


def get_product(conn, product_id: str) -> dict:
    product = _product(conn, product_id.strip().upper())
    if not product:
        raise ToolError(f"No product {product_id}.")
    variants = conn.execute(
        "SELECT id, size, color, price_cents, stock FROM variants WHERE product_id = ? ORDER BY id",
        (product["id"],),
    ).fetchall()
    return {**product, "variants": [dict(v) for v in variants]}


# ---------------- write tools ----------------

def return_items(conn, s: Session, order_id: str, item_ids: list[str], refund_method: str) -> dict:
    if refund_method not in ("original_payment", "store_credit"):
        raise ToolError("refund_method must be original_payment or store_credit.")
    if not item_ids:
        raise ToolError("Give at least one item id.")
    order = _load_order(conn, s, order_id)
    today = get_today(conn)
    items = []
    for iid in item_ids:  # check EVERY item before writing anything: all or nothing
        item = _load_item(conn, order, iid)
        if item in items:
            raise ToolError(f"Item {iid} is listed twice.")
        product = _product(conn, _variant(conn, item["variant_id"])["product_id"])
        _enforce(rules.can_return(order, item, product, today))
        items.append(item)
    with conn:  # one transaction
        for item in items:
            conn.execute("UPDATE order_items SET status = 'returned' WHERE id = ?", (item["id"],))
            conn.execute(
                "INSERT INTO returns (order_id, item_id, refund_method, amount_cents) VALUES (?,?,?,?)",
                (order["id"], item["id"], refund_method, item["price_cents"]),
            )
        _log(conn, order["id"], "return", f"{','.join(i['id'] for i in items)} via {refund_method}")
    return {
        "order_id": order["id"],
        "returned": [i["id"] for i in items],
        "refund_cents": sum(i["price_cents"] for i in items),
        "refund_method": refund_method,
        "note": "Refunds take 5 to 7 business days.",
    }


def exchange_item(conn, s: Session, order_id: str, item_id: str, new_variant_id: str) -> dict:
    order = _load_order(conn, s, order_id)
    item = _load_item(conn, order, item_id)
    current = _variant(conn, item["variant_id"])
    nxt = _variant(conn, new_variant_id)
    if not nxt:
        raise ToolError(f"No variant {new_variant_id}. Use get_product to see valid variant ids.")
    _enforce(rules.can_exchange(order, item, _product(conn, current["product_id"]), current, nxt, get_today(conn)))
    with conn:
        conn.execute("UPDATE order_items SET status = 'exchanged' WHERE id = ?", (item["id"],))
        conn.execute("UPDATE variants SET stock = MAX(stock - 1, 0) WHERE id = ?", (nxt["id"],))
        conn.execute(
            "INSERT INTO exchanges (order_id, item_id, old_variant_id, new_variant_id) VALUES (?,?,?,?)",
            (order["id"], item["id"], current["id"], nxt["id"]),
        )
        _log(conn, order["id"], "exchange", f"{item['id']}: {current['id']} to {nxt['id']}")
    return {"order_id": order["id"], "item_id": item["id"], "from": current["id"], "to": nxt["id"]}


def cancel_order(conn, s: Session, order_id: str, reason: str) -> dict:
    order = _load_order(conn, s, order_id)
    _enforce(rules.can_cancel(order))
    if order["status"] == "cancelled":
        raise ToolError(f"Order {order['id']} is already cancelled.")
    with conn:
        conn.execute("UPDATE orders SET status = 'cancelled' WHERE id = ?", (order["id"],))
        _log(conn, order["id"], "cancel", reason)
    return {"order_id": order["id"], "status": "cancelled"}


def change_address(conn, s: Session, order_id: str, new_address: str) -> dict:
    new_address = new_address.strip()
    if len(new_address) < 10:
        raise ToolError("That address looks incomplete. Ask for street, city, state and zip.")
    order = _load_order(conn, s, order_id)
    _enforce(rules.can_change_address(order))
    with conn:
        conn.execute("UPDATE orders SET shipping_address = ? WHERE id = ?", (new_address, order["id"]))
        _log(conn, order["id"], "address_change", new_address)
    return {"order_id": order["id"], "shipping_address": new_address}


# Name -> function, used by the grader to replay expected actions.
WRITE_ACTIONS = {
    "verify_user": verify_user,
    "return_items": return_items,
    "exchange_item": exchange_item,
    "cancel_order": cancel_order,
    "change_address": change_address,
}
