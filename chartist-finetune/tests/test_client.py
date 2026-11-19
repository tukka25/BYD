from client import SONNET, price


def test_cached_input_is_additive_not_subtracted():
    usage = {"input": 1000, "cache_read": 9000, "output": 0}
    assert price(usage, SONNET) == 0.00145


def test_plain_batched_price():
    usage = {"input": 1_000_000, "output": 1_000_000, "cache_read": 0}
    assert price(usage, SONNET) == 6.0
