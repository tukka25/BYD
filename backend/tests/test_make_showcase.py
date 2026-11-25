import email
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from make_showcase import (  # noqa: E402
    SHOWCASES,
    export_block,
    finished,
    model_record,
    multipart,
    parse_sse,
    served_model,
    summarize_build,
    write_dashboard,
)

STREAM = [
    b"event: status\n", b'data: {"label": "Planning the charts"}\n', b"\n",
    b"event: plan\n", b'data: {"total": 4, "sections": [], "missing_kinds": []}\n', b"\n",
    b"event: block\n", b'data: {"kind": "text", "title": "About this data"}\n', b"\n",
    b"event: skipped\n", b'data: {"index": 2, "label": "Top artists", "reason": "no figure"}\n', b"\n",
    b"event: block\n", b'data: {"kind": "chart", "title": "Popularity by genre"}\n', b"\n",
    b"event: done\n", b'data: {"total": 4}\n', b"\n",
]


def test_each_event_comes_with_its_data():
    events = list(parse_sse(STREAM))
    assert [name for name, _ in events] == ["status", "plan", "block", "skipped", "block", "done"]
    assert events[1][1]["total"] == 4


def test_crlf_lines_read_the_same():
    assert list(parse_sse(["event: done\r\n", 'data: {"total": 1}\r\n', "\r\n"])) == [("done", {"total": 1})]


def test_the_plans_total_counts_the_intro_block():
    assert summarize_build(list(parse_sse(STREAM))) == {
        "charts_planned": 3,
        "skipped": [{"label": "Top artists", "reason": "no figure"}],
        "missing_kinds": [],
    }


def test_a_build_with_no_plan_is_an_error():
    with pytest.raises(RuntimeError, match="no plan"):
        summarize_build([("status", {"label": "Planning"}), ("error", {"message": "the checks failed"})])


def test_the_export_keeps_what_the_app_saved_and_nothing_else():
    saved = {"id": "b1", "kind": "chart", "title": "T", "prompt": "q", "code": "c", "figure": {"data": []},
             "text_body": None, "source_name": "s", "chart_type": "bar", "used_fallback": False,
             "x": 0, "y": 3, "w": 6, "h": 8}
    assert export_block(saved) == {"kind": "chart", "title": "T", "chart_type": "bar", "figure": {"data": []},
                                   "text_body": None, "code": "c", "x": 0, "y": 3, "w": 6, "h": 8}


def test_the_served_model_is_read_from_the_server_command():
    ps = ("/bin/zsh\n"
          "Python -m mlx_lm server --model models/qwen3.5-9b-4bit --adapter-path runs/adapters-mlx-v2 "
          "--host 127.0.0.1 --port 8080\n")
    model = served_model(ps)
    assert model == {"base": "models/qwen3.5-9b-4bit", "adapter": "runs/adapters-mlx-v2"}
    assert model_record(model)["label"] == "lora-v2"
    assert model_record({"base": "models/qwen3.5-9b-4bit", "adapter": "runs/adapters-mlx"})["label"] == "runs/adapters-mlx"
    assert served_model("/bin/zsh\n") is None


def test_an_upload_carries_the_file_unchanged():
    body, content_type = multipart("file", "listings.xlsx", b"\x00\x01binary")
    message = email.message_from_bytes(b"Content-Type: " + content_type.encode() + b"\r\n\r\n" + body)
    (part,) = message.get_payload()
    assert part.get_param("name", header="content-disposition") == "file"
    assert part.get_filename() == "listings.xlsx"
    assert part.get_payload(decode=True) == b"\x00\x01binary"


def test_a_dashboard_is_written_compact_and_whole(tmp_path):
    path = tmp_path / "netflix.json"
    size = write_dashboard(path, {"blocks": [{"title": "a"}]})
    assert path.read_text(encoding="utf-8") == '{"blocks":[{"title":"a"}]}'
    assert size == path.stat().st_size
    assert not list(tmp_path.glob("*.tmp"))


def test_a_dashboard_over_the_limit_is_refused_naming_its_largest_block(tmp_path):
    path = tmp_path / "spotify.json"
    blocks = [{"title": "Energy vs danceability", "figure": "x" * 200}, {"title": "small"}]
    with pytest.raises(ValueError, match="Energy vs danceability"):
        write_dashboard(path, {"blocks": blocks}, limit=100)
    assert not path.exists()


def test_every_prompt_fits_the_brief_field():
    assert all(len(config["prompt"]) <= 400 for config in SHOWCASES.values())


def test_a_build_is_finished_only_when_done_arrived():
    events = list(parse_sse(STREAM))
    assert finished(events)
    assert not finished(events[:-1])
    assert not finished([])
