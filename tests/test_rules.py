from shopguard.rules import can_cancel, can_change_address, can_exchange, can_return

TODAY = "2026-11-01"


def order(**o):
    return {"id": "W1", "status": "delivered", "delivered_at": "2026-10-25", **o}


def item(**i):
    return {"id": "W1-1", "status": "ok", **i}


def product(**p):
    return {"name": "Cotton Tee", "final_sale": 0, **p}


def variant(**v):
    return {"id": "P300-M", "product_id": "P300", "stock": 10, **v}


def test_day_30_allowed_day_31_blocked():
    assert can_return(order(delivered_at="2026-10-02"), item(), product(), TODAY)[0]
    assert not can_return(order(delivered_at="2026-10-01"), item(), product(), TODAY)[0]


def test_final_sale_and_already_returned_blocked():
    assert not can_return(order(), item(), product(final_sale=1), TODAY)[0]
    assert not can_return(order(), item(status="returned"), product(), TODAY)[0]


def test_not_delivered_blocked():
    assert not can_return(order(status="shipped", delivered_at=None), item(), product(), TODAY)[0]


def test_exchange_rules():
    assert can_exchange(order(), item(), product(), variant(), variant(id="P300-L"), TODAY)[0]
    assert not can_exchange(order(), item(), product(), variant(), variant(id="P300-XL", stock=0), TODAY)[0]
    assert not can_exchange(order(), item(), product(), variant(), variant(id="P100-8", product_id="P100"), TODAY)[0]
    assert not can_exchange(order(), item(), product(), variant(), variant(), TODAY)[0]


def test_cancel_and_address_by_status():
    assert can_cancel(order(status="pending"))[0]
    for s in ("processing", "shipped", "delivered"):
        assert not can_cancel(order(status=s))[0]
    assert can_change_address(order(status="processing"))[0]
    assert not can_change_address(order(status="shipped"))[0]


def test_reasons_say_what_to_do_next():
    ok, why = can_cancel(order(status="shipped"))
    assert not ok and "return" in why
