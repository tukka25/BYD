from extract_specs import columns_in_code, consistent

CODE = "d = df.groupby('cntry_cd')['churn_cnt'].sum()\nfig = px.bar(d, x=\"cntry_cd\", y='churn_cnt')\n"


def spec(**kw):
    base = {"chart": "bar", "x": "cntry_cd", "y": "churn_cnt", "group": ""}
    base.update(kw)
    return base


def test_columns_must_appear_in_the_code():
    assert columns_in_code(spec(), CODE)
    assert not columns_in_code(spec(group="plan_tier"), CODE)


def test_consistent_needs_the_right_trace_and_area_tie_break():
    assert consistent(spec(), "bar", CODE)
    assert not consistent(spec(chart="pie"), "bar", CODE)
    assert not consistent(spec(chart="area"), "scatter", CODE)
