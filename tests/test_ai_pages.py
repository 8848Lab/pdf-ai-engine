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
    # M3: the number in SYSTEM_PROMPT is derived from len(TOOLS), so this
    # pins the count is correct AND that the prompt tracks it.
    assert len(TOOLS) == 11
    assert f"through {len(TOOLS)} tools" in SYSTEM_PROMPT
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


def test_the_system_prompt_mentions_blocks_and_pages_not_just_blocks():
    # M3: no doubled "and" before sanitize_document/the page tools, and the
    # guidance covers pages too, not only blocks.
    assert "from), and sanitize_document" not in SYSTEM_PROMPT
    assert "from), sanitize_document" in SYSTEM_PROMPT
    assert "Find the block(s) or page(s)" in SYSTEM_PROMPT
    assert "if nothing in the block or page list matches" in SYSTEM_PROMPT


def test_pages_text_says_0_based():
    # M4: _pages_text() itself, not just the system prompt, tells the model
    # indices are 0-based.
    from webui.ai.loop import _pages_text

    _load(1)
    assert "0-based" in _pages_text()


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


def test_rotate_page_result_text_reports_the_normalised_rotation_not_the_raw_request():
    # M2: -450 is normalised to 270 by rotate_page; the result text must say
    # what actually landed, not echo the raw -450 the model asked for.
    _load(1)
    result_text, is_error = _execute_tool("rotate_page", {"page_index": 0, "rotation": -450})
    assert is_error is False
    assert "270" in result_text
    assert "-450" not in result_text
    assert session.get_pages_summary()[0]["rotation"] == 270


def test_duplicate_page_result_text_reports_the_copys_index():
    _load(2)
    result_text, is_error = _execute_tool("duplicate_page", {"page_index": 0})
    assert is_error is False
    assert "index 0" in result_text
    assert "index 1" in result_text


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


def test_insert_page_tool_with_both_dimensions_explicit():
    # M4: an explicit width and height on the tool, not defaulted.
    _load(2)
    result_text, is_error = _execute_tool("insert_page", {"at_index": 1, "width": 250, "height": 175})
    assert is_error is False, result_text
    assert (session.get_pages_summary()[1]["width"], session.get_pages_summary()[1]["height"]) == (250, 175)


# ---- M1: malformed tool input is a clean tool error, not a crash --------------


@pytest.mark.parametrize("bad_input", [None, [0], "0"])
def test_execute_tool_rejects_non_dict_input(bad_input):
    _load(1)
    result_text, is_error = _execute_tool("delete_page", bad_input)
    assert is_error is True
    assert "JSON object" in result_text


def test_execute_tool_reports_a_missing_argument_by_name():
    _load(1)
    result_text, is_error = _execute_tool("rotate_page", {"page_index": 0})  # no "rotation"
    assert is_error is True
    assert "missing required argument" in result_text
    assert "rotation" in result_text


# ---- I1: stale page indices within one tool round -----------------------------


def _tool_results_from(create_mock, call_index):
    return create_mock.call_args_list[call_index].kwargs["messages"][-1]["content"]


def test_two_delete_page_calls_in_one_round_the_second_is_refused_as_stale():
    _load(3)  # P0, P1, P2
    responses = [
        _fake_response(
            [
                _tool_use_block("c1", "delete_page", {"page_index": 0}),
                _tool_use_block("c2", "delete_page", {"page_index": 1}),
            ],
            "tool_use",
        ),
        _fake_response([_text_block("done")], "end_turn"),
    ]
    with patch("webui.ai.providers.anthropic.anthropic.Anthropic") as mock_cls:
        mock_client = mock_cls.return_value
        mock_client.messages.create.side_effect = responses
        run_instruction("delete the first two pages", provider="anthropic", api_key="k")

    # Only the FIRST delete actually happened; the stale second index would
    # otherwise have deleted the wrong (already-shifted) page.
    assert _page_texts() == [["P1"], ["P2"]]
    tool_results = _tool_results_from(mock_client.messages.create, 1)
    c2_result = next(r for r in tool_results if r.get("tool_use_id") == "c2")
    assert c2_result["is_error"] is True
    assert "delete_page" in c2_result["content"]


def test_two_rotate_page_calls_in_one_round_both_apply():
    # rotate_page does not shift indices, so it must never trigger the
    # refusal, including a second rotate_page later in the same round.
    _load(2)
    responses = [
        _fake_response(
            [
                _tool_use_block("c1", "rotate_page", {"page_index": 0, "rotation": 90}),
                _tool_use_block("c2", "rotate_page", {"page_index": 1, "rotation": 180}),
            ],
            "tool_use",
        ),
        _fake_response([_text_block("done")], "end_turn"),
    ]
    with patch("webui.ai.providers.anthropic.anthropic.Anthropic") as mock_cls:
        mock_client = mock_cls.return_value
        mock_client.messages.create.side_effect = responses
        run_instruction("rotate both pages", provider="anthropic", api_key="k")

    assert [p["rotation"] for p in session.get_pages_summary()] == [90, 180]
    tool_results = _tool_results_from(mock_client.messages.create, 1)
    assert all(r.get("is_error") is not True for r in tool_results if r.get("type") == "tool_result")


def test_move_page_then_insert_block_in_one_round_the_insert_block_is_refused():
    _load(3)  # P0, P1, P2
    responses = [
        _fake_response(
            [
                _tool_use_block("c1", "move_page", {"page_index": 2, "to_index": 0}),
                _tool_use_block(
                    "c2", "insert_block", {"page_index": 2, "bbox": [72, 700, 200, 720], "text": "x", "size": 12, "font": None}
                ),
            ],
            "tool_use",
        ),
        _fake_response([_text_block("done")], "end_turn"),
    ]
    with patch("webui.ai.providers.anthropic.anthropic.Anthropic") as mock_cls:
        mock_client = mock_cls.return_value
        mock_client.messages.create.side_effect = responses
        run_instruction("move the last page to the front, then add text to page 2", provider="anthropic", api_key="k")

    # move_page applied; insert_block did NOT draw anything on the
    # (now-different) page 2.
    assert _page_texts() == [["P2"], ["P0"], ["P1"]]
    tool_results = _tool_results_from(mock_client.messages.create, 1)
    c2_result = next(r for r in tool_results if r.get("tool_use_id") == "c2")
    assert c2_result["is_error"] is True
    assert "move_page" in c2_result["content"]


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
