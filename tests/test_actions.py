import pytest

from shopguard import actions as A

MAYA = dict(email="maya.lee@example.com", zip="94110")


def count(db, table):
    return db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_blocks_before_verification(db):
    with pytest.raises(A.ToolError, match="Verify"):
        A.get_order(db, A.Session(), "W1043")


def test_verify_wrong_zip(db):
    with pytest.raises(A.ToolError):
        A.verify_user(db, A.Session(), "maya.lee@example.com", "99999")


def test_hides_other_customers_orders(db):
    s = A.Session()
    A.verify_user(db, s, **MAYA)
    with pytest.raises(A.ToolError, match="No order W1050"):
        A.get_order(db, s, "W1050")


def test_return_in_window(db):
    s = A.Session()
    A.verify_user(db, s, **MAYA)
    r = A.return_items(db, s, "W1043", ["W1043-1"], "original_payment")
    assert r["refund_cents"] == 8900 and count(db, "returns") == 1


def test_late_return_changes_nothing(db):
    s = A.Session()
    A.verify_user(db, s, **MAYA)
    with pytest.raises(A.ToolError, match="window"):
        A.return_items(db, s, "W1042", ["W1042-1"], "original_payment")
    assert count(db, "returns") == 0


def test_all_or_nothing_with_final_sale(db):
    s = A.Session()
    A.verify_user(db, s, email="priya.nair@example.com", zip="60614")
    with pytest.raises(A.ToolError, match="final sale"):
        A.return_items(db, s, "W1060", ["W1060-2", "W1060-1"], "store_credit")
    assert count(db, "returns") == 0


def test_exchange_out_of_stock_and_ok(db):
    s = A.Session()
    A.verify_user(db, s, email="dan.brooks@example.com", zip="98103")
    with pytest.raises(A.ToolError, match="out of stock"):
        A.exchange_item(db, s, "W1071", "W1071-1", "P300-XL")
    A.exchange_item(db, s, "W1071", "W1071-1", "P300-L")
    assert db.execute("SELECT stock FROM variants WHERE id='P300-L'").fetchone()[0] == 9


def test_session_file_persists(tmp_path, db):
    p = tmp_path / "s.json"
    A.verify_user(db, A.Session.load(p), **MAYA)
    assert A.Session.load(p).user_id == "U1001"


def test_rules_off_ablation(db, monkeypatch):
    monkeypatch.setenv("SHOPGUARD_RULES", "off")
    s = A.Session()
    A.verify_user(db, s, **MAYA)
    A.return_items(db, s, "W1042", ["W1042-1"], "original_payment")  # allowed when rules are off
    assert count(db, "returns") == 1
