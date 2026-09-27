### Task 7: The refusal gate (R5, R12, P3, P4)

**Files:**
- Modify: `engine/operations.py`:
  - the `engine.geometry` import (add `OTHER_DRAWING`, `TEXT_DRAWING`, `drawing_refusal`)
  - a new `_refuse_unsupported_drawing` helper, placed before `_erase_region`
  - one gate call in each of the six targeted operations; two in `move_block`
  - `move_block`'s destination binding
- Modify: `tests/test_page_geometry.py` (append)

**Interfaces:**
- Consumes:
  - `engine.geometry.drawing_refusal`, `TEXT_DRAWING` and `OTHER_DRAWING` from Task 2
  - `build_page`, `block`, `exported` and `fingerprint` from Task 3; `_inherited_rotation_page` from Task 5; `BLUE`, `IMAGE_RECT` and `_png` from Task 6
- Produces: `engine.operations._refuse_unsupported_drawing(page, page_index, kind) -> None`

**Gate placement, one call right after each operation's validation, before anything else:**

| Operation | After line | Gate |
|---|---|---|
| `redact_region` | `page, rect = _validate_target(handle, page_index, bbox)` | `page, page_index, OTHER_DRAWING` |
| `replace_text` | `page, rect = _validate_target(handle, page_index, target.bbox)` | `page, page_index, TEXT_DRAWING` |
| `delete_block` | `page, rect = _validate_target(handle, page_index, target.bbox)` | `page, page_index, OTHER_DRAWING` |
| `move_block` | `source_page, source_rect = _validate_target(...)` | `source_page, page_index, OTHER_DRAWING` (P4: the source is erased) |
| `move_block` | `destination_page, destination_rect = _validate_target(...)` | `destination_page, dest_index, TEXT_DRAWING` |
| `insert_block` | `page, rect = _validate_target(handle, page_index, bbox)` | `page, page_index, TEXT_DRAWING` |
| `replace_image` | `page, rect = _validate_target(handle, page_index, target.bbox)` | `page, page_index, OTHER_DRAWING` |

The three `page, rect = _validate_target(...)` lines are not unique across the file. Locate each one by its operation.

Both `move_block` gates run before the source erase (`_clean_erase(source_page, source_rect)`), and nothing in `move_block` mutates the document before that erase. The coordinator confirmed this against the real body.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_page_geometry.py`:

```python
OVERHANG_CASES = {
    "left": ("[-40 0 612 792]", True),
    "top": ("[0 0 612 830]", True),
    "all-four": ("[-40 -60 660 820]", True),
    "bottom": ("[0 -60 612 792]", False),
    "right": ("[0 0 660 792]", False),
    "contained": ("[40 60 580 740]", False),
}
TEXT_OPS = {
    "replace_text": lambda h, b: replace_text(h, 0, b, b.text),
    "move_block": lambda h, b: move_block(h, 0, b, offset=(0, -100)),
    "insert_block": lambda h, b: insert_block(h, 0, (72, 300, 400, 320), "NEW", 12.0),
}
OTHER_OPS = {
    "redact_region": lambda h, b: redact_region(h, 0, b.bbox),
    "delete_block": lambda h, b: delete_block(h, 0, b),
}


@pytest.mark.parametrize("case", sorted(OVERHANG_CASES))
@pytest.mark.parametrize("op", sorted(TEXT_OPS))
def test_text_operations_refuse_exactly_the_overhang_pages(op, case):
    cropbox, refused = OVERHANG_CASES[case]
    doc, handle = parse(build_page(cropbox=cropbox))
    before = fingerprint(handle)
    if refused:
        with pytest.raises(ValueError, match="CropBox"):
            TEXT_OPS[op](handle, block(doc, "LOW-MARKER"))
        assert fingerprint(handle) == before
    else:
        TEXT_OPS[op](handle, block(doc, "LOW-MARKER"))  # no false positive


@pytest.mark.parametrize("op", sorted(OTHER_OPS))
def test_redaction_and_erasing_still_work_on_an_overhang_page(op):
    doc, handle = parse(build_page(cropbox=OVERHANG_CASES["all-four"][0]))
    OTHER_OPS[op](handle, block(doc, "LOW-MARKER"))
    assert "LOW-MARKER" not in exported(handle)[0].get_text()


def test_text_operations_are_allowed_on_a_negative_origin_mediabox():
    # Regression guard: mediabox.contains(cropbox) would refuse this page,
    # which draws correctly.
    doc, handle = parse(build_page(mediabox="[-100 -100 512 692]"))
    replace_text(handle, 0, block(doc, "LOW-MARKER"), "LOW-MARKER")  # must not raise


ALL_TARGETED = {**TEXT_OPS, **OTHER_OPS}


# 0.5 as well as 1.5: a gate written as "unit > 1" passes every 1.5 case.
@pytest.mark.parametrize("unit", (0.5, 1.5))
@pytest.mark.parametrize("op", sorted(ALL_TARGETED))
def test_every_operation_refuses_a_user_unit_page_with_the_owners_warning(op, unit):
    doc, handle = parse(build_page(user_unit=unit))
    before = fingerprint(handle)
    with pytest.raises(ValueError) as caught:
        ALL_TARGETED[op](handle, block(doc, "LOW-MARKER"))
    message = str(caught.value)
    assert "/UserUnit" in message
    assert "nothing was changed" in message
    assert "Support is planned" in message
    assert fingerprint(handle) == before


@pytest.mark.parametrize("unit", (0.5, 1.5))
def test_replace_image_refuses_a_user_unit_page(unit):
    doc, handle = parse(build_page(user_unit=unit, image_rect=IMAGE_RECT))
    before = fingerprint(handle)
    with pytest.raises(ValueError, match="Support is planned"):
        replace_image(handle, 0, doc.pages[0].images[0], _png(BLUE))
    assert fingerprint(handle) == before


@pytest.mark.parametrize("op", sorted(ALL_TARGETED))
def test_every_operation_refuses_a_malformed_rotation(op):
    # P3, with the gate's own message: the marker sits on the page, so the
    # bbox check passes and only the gate can refuse.
    doc, handle = parse(build_page(rotate_raw="45"))
    before = fingerprint(handle)
    with pytest.raises(ValueError, match="invalid rotation"):
        ALL_TARGETED[op](handle, block(doc, "LOW-MARKER"))
    assert fingerprint(handle) == before


def test_replace_image_refuses_a_malformed_rotation():
    doc, handle = parse(build_page(rotate_raw="45", image_rect=IMAGE_RECT))
    before = fingerprint(handle)
    with pytest.raises(ValueError, match="invalid rotation"):
        replace_image(handle, 0, doc.pages[0].images[0], _png(BLUE))
    assert fingerprint(handle) == before


def test_an_inherited_malformed_rotation_is_refused():
    # /Rotate 45 set only on the /Pages parent reaches the gate through the
    # Task 2 reader's /Parent walk.
    doc, handle = parse(_inherited_rotation_page("45"))
    before = fingerprint(handle)
    with pytest.raises(ValueError, match="invalid rotation"):
        redact_region(handle, 0, block(doc, "LOW-MARKER").bbox)
    assert fingerprint(handle) == before


def test_move_block_refuses_when_the_source_page_uses_user_unit():
    # P4: the source is erased, and an erase paints a fill.
    doc, handle = parse(build_page(user_unit=1.5, extra_pages=1))
    before = fingerprint(handle)
    with pytest.raises(ValueError, match="Page 0 uses PDF /UserUnit"):
        move_block(handle, 0, block(doc, "LOW-MARKER"),
                   destination_page_index=1, target_position=(72, 100))
    assert fingerprint(handle) == before


def _plain_page_then_user_unit_page():
    source = fitz.open(stream=build_page(extra_pages=1), filetype="pdf")
    source[1].insert_text((72, 100), "PAGE-ONE", fontsize=12)
    source.xref_set_key(source[1].xref, "UserUnit", "1.5")
    data = source.tobytes()
    source.close()
    return data


def test_move_block_refuses_an_unsupported_destination_page_and_keeps_the_source():
    # P4, the other direction: a plain source page moving onto a /UserUnit
    # page. The destination gate must fire before the source is erased.
    doc, handle = parse(_plain_page_then_user_unit_page())
    before = fingerprint(handle)
    with pytest.raises(ValueError, match="Page 1 uses PDF /UserUnit"):
        move_block(handle, 0, block(doc, "LOW-MARKER"),
                   destination_page_index=1, target_position=(72, 300))
    assert fingerprint(handle) == before
    assert "LOW-MARKER" in exported(handle)[0].get_text()


def test_gate_uses_the_target_pages_own_geometry():
    # Review Focus 1: page 1 uses /UserUnit, page 0 is plain. Page 0 must
    # stay fully editable, and page 1 must be refused.
    doc, handle = parse(_plain_page_then_user_unit_page())
    redact_region(handle, 0, block(doc, "LOW-MARKER").bbox)  # page 0: allowed
    page_one = next(b for b in doc.pages[1].text_blocks if "PAGE-ONE" in b.text)
    with pytest.raises(ValueError, match="Page 1 uses PDF /UserUnit"):
        redact_region(handle, 1, page_one.bbox)
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `timeout 600 ./.venv/Scripts/python.exe -m pytest tests/test_page_geometry.py -v`

Expected — measured on the engine after Task 6: **31 failed, 118 passed.**
- The nine refused cases of `test_text_operations_refuse_exactly_the_overhang_pages` (left, top and all-four, for each of the three text operations) fail with `DID NOT RAISE`.
- Every case of `test_every_operation_refuses_a_user_unit_page_with_the_owners_warning` (10) and `test_replace_image_refuses_a_user_unit_page` (2) fails with `DID NOT RAISE`.
- Every case of `test_every_operation_refuses_a_malformed_rotation` (5), plus `test_replace_image_refuses_a_malformed_rotation` and `test_an_inherited_malformed_rotation_is_refused`, fails with `DID NOT RAISE`.
- Both `move_block` refusal tests and `test_gate_uses_the_target_pages_own_geometry` fail with `DID NOT RAISE`.
- Already passing, and kept as guards: the nine no-overhang cases, redaction and erasing on an overhang page, and the negative-origin MediaBox.

- [ ] **Step 3: Implement the gate helper**

Add `OTHER_DRAWING`, `TEXT_DRAWING` and `drawing_refusal` to the `engine.geometry` import in `engine/operations.py`. Then add, immediately before `def _erase_region(`:

```python
def _refuse_unsupported_drawing(page: fitz.Page, page_index: int, kind: str) -> None:
    """Raise before any mutation if this page cannot be drawn on correctly.

    See engine.geometry.drawing_refusal for the rules and the evidence. Every
    targeted operation calls this right after validating its target.
    """
    reason = drawing_refusal(page, page_index, kind)
    if reason is not None:
        raise ValueError(reason)
```

- [ ] **Step 4: Insert the seven gate calls**

Following the table above, insert one line after each named validation line. For example, `redact_region` becomes:

```python
    page, rect = _validate_target(handle, page_index, bbox)
    _refuse_unsupported_drawing(page, page_index, OTHER_DRAWING)
    _erase_region(page, rect, fill=(0, 0, 0))
```

In `move_block`, bind the destination page from its own validation, so the gate checks exactly the page that was validated. Delete the line:

```python
    destination_page = handle[dest_index]
```

and replace:

```python
    _, destination_rect = _validate_target(handle, dest_index, destination_bbox)
```

with:

```python
    destination_page, destination_rect = _validate_target(handle, dest_index, destination_bbox)
    _refuse_unsupported_drawing(destination_page, dest_index, TEXT_DRAWING)
```

Nothing between the deleted line and the validation uses `destination_page`; confirm with `grep -n destination_page engine/operations.py` before and after. The source gate goes right after `source_page, source_rect = _validate_target(handle, page_index, target.bbox)`:

```python
    _refuse_unsupported_drawing(source_page, page_index, OTHER_DRAWING)
```

Also add one sentence to the `Raises:` section of each of the six docstrings: *"or the page cannot be drawn on correctly (malformed /Rotate, /UserUnit, or — for text — a CropBox overhang); see engine.geometry.drawing_refusal."*

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `timeout 600 ./.venv/Scripts/python.exe -m pytest tests/test_page_geometry.py -v`
Expected: 149 passed.

- [ ] **Step 6: Mutation check — each gate is load-bearing**

Back up the file first, then delete each of the seven gate calls in turn, restoring from the backup between runs:

```bash
cp engine/operations.py "$TEMP/operations.py.task7"
# delete one gate line, run the file, then:
cp "$TEMP/operations.py.task7" engine/operations.py
```

Do not use `git stash`.

Expected failure counts, measured by the coordinator:

| Gate removed | Tests that fail |
|---|---|
| `redact_region` | 5 |
| `replace_text` | 6 |
| `delete_block` | 3 |
| `move_block` source | 1 |
| `move_block` destination | 4 |
| `insert_block` | 6 |
| `replace_image` | 3 |

Paste a seven-row table into your report: the gate removed, and the names of the tests that failed. After the last restore, confirm that `git diff` shows only your intended changes, then delete the backup.

- [ ] **Step 7: Run the full suite and commit**

Run: `timeout 600 ./.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: all pass.

```bash
git add engine/operations.py tests/test_page_geometry.py
git commit -m "feat: refuse drawing on pages the engine cannot render correctly

Before any mutation, every targeted operation now refuses a page with a
malformed /Rotate, with /UserUnit scaling, or -- for text drawing only -- a
CropBox whose top-left extends past the MediaBox. Redaction is still allowed
on overhang pages, where it is verified correct. The /UserUnit refusal is
worded as the owner asked: it names the cause, says nothing changed, and
says support is planned.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_016ns89haVgmSD9aXKkdw3Ka"
```

---

