from pricing import final_price


def test_discount():
    # Deliberately fails until a later lesson implements the repair workflow.
    assert final_price(100, 0.2) == 80
