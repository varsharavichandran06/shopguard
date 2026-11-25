from data.seed import seed
from shopguard.guardrails import looks_like_card
from shopguard.search import PolicyIndex


def test_seed_is_deterministic(tmp_path):
    from shopguard.db import open_db

    def rows(path):
        conn = open_db(path)
        out = [tuple(r) for r in conn.execute("SELECT * FROM orders ORDER BY id")]
        conn.close()
        return out

    assert rows(seed(tmp_path / "a.db")) == rows(seed(tmp_path / "b.db"))


def test_bm25_search_and_floor():
    idx = PolicyIndex(use_vectors=False)
    assert idx.search("price match", k=3)[0]["doc_id"] == "faq#price-matching"
    assert idx.search("capital of france", k=3) == []


def test_card_numbers_are_caught_but_phone_numbers_are_not():
    assert looks_like_card("my card is 4111 1111 1111 1111")
    assert not looks_like_card("order W1043, zip 94110")
    assert not looks_like_card("call me at 415 555 0134")
