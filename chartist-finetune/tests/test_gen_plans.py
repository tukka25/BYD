from gen_plans import keep_charts, keep_directions


def test_only_clean_and_full_plans_become_training_rows():
    three = [{}, {}, {}]
    assert keep_directions(three, [])
    assert not keep_directions(three, ["direction 4: ..."])
    assert not keep_directions([{}, {}], [])
    assert keep_charts(three, []) and not keep_charts(three, ["chart 2: ..."])
