"""Merge B's AI layer: the five page tools and the pages summary the model is
given (spec R10/E3)."""
import json
from unittest.mock import patch

import pymupdf as fitz
import pytest

pytest.importorskip("anthropic", reason="webui/ai tests need the `ai` extras group installed")

from webui import session  # noqa: E402
from webui.ai import run_instruction  # noqa: E402
from webui.ai.tools import SYSTEM_PROMPT, TOOLS, _execute_tool  # noqa: E402
from tests.test_ai import _fake_response, _text_block, _tool_use_block  # noqa: E402

PAGE_TOOLS = ("delete_page", "move_page", "rotate_page", "insert_page", "duplicate_page")


@pytest.fixture(autouse=True)
def _reset_session():
    session.reset()
    yield
    session.reset()


def _load(count):
    doc = fitz.open()
    for i in range(count):
        doc.new_page(width=612, height=792).insert_text((72, 100), f"P{i}", fontsize=12)
    session.load_document(doc.tobytes())


def _page_texts():
    blocks = session.get_blocks_summary()
    return [[b["text"] for b in blocks if b["page_index"] == p["index"]] for p in session.get_pages_summary()]


def test_all_five_page_tools_are_registered_in_strict_mode():
    by_name = {tool["name"]: tool for tool in TOOLS}
    assert len(TOOLS) == 11
    for name in PAGE_TOOLS:
        schema = by_name[name]["input_schema"]
        assert by_name[name]["strict"] is True
        assert schema["additionalProperties"] is False
        # Strict mode: every property is required; optional ones are nullable.
        assert set(schema["required"]) == set(schema["properties"])


def test_insert_page_dimensions_are_nullable():
    props = next(t for t in TOOLS if t["name"] == "insert_page")["input_schema"]["properties"]
    assert props["width"]["type"] == ["number", "null"]
    assert props["height"]["type"] == ["number", "null"]


def test_the_descriptions_state_the_semantics_the_model_would_get_wrong():
    by_name = {tool["name"]: tool["description"] for tool in TOOLS}
    assert "final-index" in by_name["move_page"]
    assert "ABSOLUTE" in by_name["rotate_page"]
    assert "0-BASED" in SYSTEM_PROMPT and "index 0" in SYSTEM_PROMPT


@pytest.mark.parametrize(
    "name, tool_input, expected",
    [
        ("delete_page", {"page_index": 0}, [["P1"], ["P2"]]),
        ("move_page", {"page_index": 2, "to_index": 0}, [["P2"], ["P0"], ["P1"]]),
        ("insert_page", {"at_index": 3, "width": None, "height": None}, [["P0"], ["P1"], ["P2"], []]),
        ("duplicate_page", {"page_index": 1}, [["P0"], ["P1"], ["P1"], ["P2"]]),
    ],
)
def test_each_page_tool_changes_the_document(name, tool_input, expected):
    _load(3)
    result_text, is_error = _execute_tool(name, tool_input)
    assert is_error is False, result_text
    assert _page_texts() == expected


def test_rotate_page_tool_sets_the_rotation():
    _load(2)
    result_text, is_error = _execute_tool("rotate_page", {"page_index": 1, "rotation": 180})
    assert is_error is False
    assert [p["rotation"] for p in session.get_pages_summary()] == [0, 180]


@pytest.mark.parametrize(
    "name, tool_input",
    [
        ("delete_page", {"page_index": 7}),
        ("rotate_page", {"page_index": 0, "rotation": 45}),
        ("insert_page", {"at_index": 0, "width": -1, "height": None}),
    ],
)
def test_a_refused_page_tool_call_is_a_tool_error_that_changes_nothing(name, tool_input):
    _load(2)
    before = (session.get_pages_summary(), session.get_blocks_summary())
    result_text, is_error = _execute_tool(name, tool_input)
    assert is_error is True
    assert "Nothing was changed" in result_text
    assert (session.get_pages_summary(), session.get_blocks_summary()) == before


def _pages_in(text):
    return json.loads(text.split("rotation is in degrees):\n", 1)[1])


def test_the_model_is_shown_the_pages_first_and_after_every_round():
    # A blank page has no blocks: without the pages summary the model could
    # not see it at all.
    _load(1)
    seen = []

    def scripted(*args, **kwargs):
        messages = kwargs["messages"]
        last = messages[-1]["content"]
        if isinstance(last, str):
            seen.append(_pages_in(last))
            return _fake_response(
                [_tool_use_block("c1", "insert_page", {"at_index": 1, "width": None, "height": None})],
                "tool_use",
            )
        pages_block = next(b for b in last if b["type"] == "text" and "Current pages" in b["text"])
        seen.append(_pages_in(pages_block["text"]))
        assert last[-1]["text"].startswith("Current blocks")  # blocks stay last
        return _fake_response([_text_block("Added a blank page.")], "end_turn")

    with patch("webui.ai.providers.anthropic.anthropic.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.side_effect = scripted
        summary = run_instruction("add a blank page at the end", provider="anthropic", api_key="k")

    assert summary == "Added a blank page."
    assert [len(pages) for pages in seen] == [1, 2]
    assert seen[1][1] == {"index": 1, "width": 612.0, "height": 792.0, "rotation": 0}
