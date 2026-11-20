"""Business rules as pure functions. No database, no network, no real clock.

Each returns (True, "") or (False, reason). Reasons tell the model what to do next.
"""
from datetime import date

RETURN_WINDOW_DAYS = 30
Check = tuple[bool, str]
OK: Check = (True, "")


def days_since(date_iso: str, today_iso: str) -> int:
    return (date.fromisoformat(today_iso) - date.fromisoformat(date_iso)).days


def can_return(order: dict, item: dict, product: dict, today: str) -> Check:
    if order["status"] != "delivered" or not order["delivered_at"]:
        return False, f"Order {order['id']} is {order['status']}. Only delivered orders can be returned."
    if item["status"] != "ok":
        return False, f"Item {item['id']} was already {item['status']}."
    if product["final_sale"] == 1:
        return False, f"{product['name']} is final sale and cannot be returned or exchanged."
    days = days_since(order["delivered_at"], today)
    if days > RETURN_WINDOW_DAYS:
        return False, (
            f"Delivered {days} days ago. The return window is {RETURN_WINDOW_DAYS} days. "
            "Do not offer a refund or store credit."
        )
    return OK


def can_exchange(order: dict, item: dict, product: dict, current: dict, nxt: dict, today: str) -> Check:
    ok, why = can_return(order, item, product, today)  # same window and final sale rules
    if not ok:
        return ok, why
    if nxt["product_id"] != current["product_id"]:
        return False, "Exchanges must be for the same product in a different size or color."
    if nxt["id"] == current["id"]:
        return False, "That is the same variant the customer already has."
    if nxt["stock"] < 1:
        return False, f"{nxt['id']} is out of stock. Offer a return or a different size."
    return OK


def can_cancel(order: dict) -> Check:
    if order["status"] == "pending":
        return OK
    return False, (
        f"Order {order['id']} is {order['status']}. Only pending orders can be cancelled. "
        "If it has shipped, offer a return after delivery."
    )


def can_change_address(order: dict) -> Check:
    if order["status"] in ("pending", "processing"):
        return OK
    return False, f"Order {order['id']} is {order['status']}. The address can only change before it ships."
