import pandas as pd

from app.services.agents.layout import intro_html, lay_out
from app.services.agents.profiler import profile_table


def s(chart, title="t"):
    return {"chart": chart, "title": title}


def test_numbers_first_then_trends_then_pairs():
    placed = lay_out([s("bar", "b1"), s("kpi", "k1"), s("line", "l1"), s("kpi", "k2"), s("pie", "p1")], top=3)
    assert [p.spec["title"] for p in placed] == ["k1", "k2", "l1", "b1", "p1"]
    k1, k2, line, bar, pie = placed
    assert (k1.x, k1.y, k1.w, k1.h) == (0, 3, 4, 4) and (k2.x, k2.w) == (4, 4)
    assert (line.x, line.y, line.w) == (0, 7, 12)
    assert (bar.x, bar.y, bar.w, pie.x, pie.y) == (0, 16, 6, 6, 16)


def test_four_numbers_share_a_row():
    placed = lay_out([s("kpi") for _ in range(4)])
    assert [p.w for p in placed] == [3, 3, 3, 3] and {p.y for p in placed} == {0}


def test_odd_chart_out_takes_the_full_width():
    placed = lay_out([s("bar"), s("pie"), s("box")])
    assert (placed[2].x, placed[2].w) == (0, 12)


def test_intro_is_escaped_and_names_the_charts():
    profile = profile_table("<b>sales</b>", pd.DataFrame({"a": [1, 2, 3]}))
    text = intro_html([profile], "revenue <script>", [s("bar", "Revenue by region")])
    assert "&lt;b&gt;sales&lt;/b&gt;" in text and "&lt;script&gt;" in text
    assert "Revenue by region" in text
