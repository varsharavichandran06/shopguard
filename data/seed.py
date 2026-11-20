"""Build data/store.db from scratch. Same output every run.

Run:  python -m data.seed            (or: python data/seed.py)
"""
import os
import random
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shopguard.config import SCHEMA_PATH, STORE_DB, STORE_TODAY  # noqa: E402
from shopguard.db import open_db  # noqa: E402

TODAY = date.fromisoformat(STORE_TODAY)


def days_ago(n: int) -> str:
    return (TODAY - timedelta(days=n)).isoformat()


PRODUCTS = [
    # id, name, category, final_sale, sizes, color, price_cents
    ("P100", "Trail Running Shoes", "footwear", 0, ["7", "8", "9", "10"], "black", 12000),
    ("P200", "Rain Jacket", "outerwear", 0, ["S", "M", "L"], "navy", 8900),
    ("P300", "Cotton Tee", "tops", 0, ["S", "M", "L", "XL"], "white", 2500),
    ("P400", "Clearance Sunglasses", "accessories", 1, ["ONE"], "tortoise", 3000),
    ("P500", "Wool Beanie", "accessories", 0, ["ONE"], "grey", 2200),
    ("P600", "Commuter Backpack", "bags", 0, ["ONE"], "olive", 7500),
    ("P700", "Smart Coffee Maker", "home", 0, ["ONE"], "steel", 24900),
]
OUT_OF_STOCK = {"P300-XL"}  # used by an exchange test

# Anchor customers. Each order exists for a test scenario. (placed, delivered) are days ago.
ANCHORS = [
    (("U1001", "Maya Lee", "maya.lee@example.com", "94110", "12 Valencia St, San Francisco, CA 94110"), [
        ("W1042", "delivered", "card", 50, 45, ["P100-8"]),            # too late to return (45 days)
        ("W1043", "delivered", "card", 14, 10, ["P200-M"]),            # can return
    ]),
    (("U1002", "Omar Haddad", "omar.h@example.com", "10027", "410 W 120th St, New York, NY 10027"), [
        ("W1050", "pending", "paypal", 1, None, ["P500-ONE", "P600-ONE"]),  # can cancel
        ("W1051", "shipped", "card", 3, None, ["P300-M"]),                 # cannot cancel
    ]),
    (("U1003", "Priya Nair", "priya.nair@example.com", "60614", "2201 N Clark St, Chicago, IL 60614"), [
        ("W1060", "delivered", "card", 8, 5, ["P400-ONE", "P300-S"]),  # one final sale, one normal
    ]),
    (("U1004", "Dan Brooks", "dan.brooks@example.com", "98103", "3500 Fremont Ave N, Seattle, WA 98103"), [
        ("W1070", "processing", "gift_card", 2, None, ["P200-L"]),        # address change ok
        ("W1071", "delivered", "card", 25, 20, ["P300-M", "P300-M"]),    # exchange M to L ok, XL out of stock
    ]),
    (("U1005", "Lena Park", "lena.park@example.com", "30307", "88 Moreland Ave, Atlanta, GA 30307"), [
        ("W1080", "delivered", "card", 35, 30, ["P600-ONE"]),          # exactly day 30: still allowed
        ("W1081", "cancelled", "card", 9, None, ["P500-ONE"]),
    ]),
    (("U1006", "Maya Lee", "maya.l@example.com", "73301", "9 Congress Ave, Austin, TX 73301"), [  # same name as U1001
        ("W1090", "delivered", "paypal", 6, 3, ["P100-9"]),
    ]),
    (("U1007", "Sam Ortiz", "sam.ortiz@example.com", "02139", "77 Mass Ave, Cambridge, MA 02139"), [
        ("W1100", "delivered", "card", 12, 7, ["P700-ONE"]),           # over $200: damaged claims go to a human
        ("W1101", "shipped", "paypal", 2, None, ["P100-10"]),          # shipped: no address change
    ]),
]

FIRST = ["Ava", "Ben", "Chloe", "Diego", "Ella", "Farah", "Gus", "Hana", "Ivan", "Jade", "Kofi", "Lucia", "Max", "Nia", "Owen"]
LAST = ["Adams", "Bose", "Cruz", "Diaz", "Evans", "Fox", "Garcia", "Huang", "Ito", "Jones", "Khan", "Lopez", "Moore", "Ng", "Olsen"]


def seed(db_path: Path = STORE_DB) -> Path:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()  # always start clean
    conn = open_db(db_path)
    conn.executescript(SCHEMA_PATH.read_text())
    rng = random.Random(42)  # seeded: same "random" filler every run
    price: dict[str, int] = {}

    def add_order(user_id, address, oid, status, pay, placed, delivered, items):
        conn.execute(
            "INSERT INTO orders VALUES (?,?,?,?,?,?,?)",
            (oid, user_id, status, pay, days_ago(placed), None if delivered is None else days_ago(delivered), address),
        )
        for i, vid in enumerate(items, 1):
            if vid not in price:
                raise ValueError(f"Unknown variant {vid} in {oid}")  # fail fast on typos
            conn.execute(
                "INSERT INTO order_items (id, order_id, variant_id, price_cents) VALUES (?,?,?,?)",
                (f"{oid}-{i}", oid, vid, price[vid]),
            )

    with conn:  # one transaction: all or nothing
        conn.execute("INSERT INTO store_config VALUES ('store_today', ?)", (STORE_TODAY,))
        for pid, name, cat, final, sizes, color, cents in PRODUCTS:
            conn.execute("INSERT INTO products VALUES (?,?,?,?)", (pid, name, cat, final))
            for size in sizes:
                vid = f"{pid}-{size}"
                stock = 0 if vid in OUT_OF_STOCK else 10
                conn.execute("INSERT INTO variants VALUES (?,?,?,?,?,?)", (vid, pid, size, color, cents, stock))
                price[vid] = cents

        for user, orders in ANCHORS:
            conn.execute("INSERT INTO users VALUES (?,?,?,?,?)", user)
            for o in orders:
                add_order(user[0], user[4], *o)

        variant_ids = list(price)
        order_no = 2001
        for i in range(15):
            uid = f"U{2001 + i}"
            zip_code = str(rng.randint(10000, 99999))
            address = f"{rng.randint(1, 999)} Main St, Springfield, {zip_code}"
            email = f"{FIRST[i].lower()}.{LAST[i].lower()}@example.com"
            conn.execute("INSERT INTO users VALUES (?,?,?,?,?)", (uid, f"{FIRST[i]} {LAST[i]}", email, zip_code, address))
            for _ in range(rng.randint(1, 3)):
                status = rng.choice(["pending", "processing", "shipped", "delivered", "delivered", "cancelled"])
                placed = rng.randint(2, 60)
                delivered = max(0, placed - rng.randint(3, 6)) if status == "delivered" else None
                items = [rng.choice(variant_ids) for _ in range(rng.randint(1, 3))]
                add_order(uid, address, f"W{order_no}", status, rng.choice(["card", "paypal", "gift_card"]), placed, delivered, items)
                order_no += 1
    conn.close()
    return db_path


if __name__ == "__main__":
    path = seed(Path(os.environ.get("STORE_DB", STORE_DB)))
    conn = open_db(path)
    n = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("users", "orders", "order_items")}
    print(f"Seeded {path}: {n['users']} users, {n['orders']} orders, {n['order_items']} items")
