"""Joined tables, told to the planner in a line each.

A connection's declared foreign keys become joined tables (orders+customers: each
order with its customer's columns). The planner reads them like any other table;
this line says what each one is, so it knows `customers.region` is the region of
the order's customer.
"""
from __future__ import annotations

MAX_LINKS = 4


def render_links(links: list[dict]) -> str:
    if not links:
        return ""
    lines = ["Joined tables you can use (each row of the first table with its match in the second):"]
    for link in links[:MAX_LINKS]:
        on = ", ".join(f"{link['child']}.{c} = {link['parent']}.{p}"
                       for c, p in zip(link["child_columns"], link["parent_columns"]))
        lines.append(f"- {link['child']}+{link['parent']}: joined on {on}; "
                     f"columns from {link['parent']} are named {link['parent']}.<column>")
    return "\n".join(lines)
