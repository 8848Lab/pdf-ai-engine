### Task 5: Redaction fill placement (R11)

**Files:**
- Modify: `engine/operations.py`:
  - the `engine.geometry` import (add `at_rotation_zero`)
  - `_erase_region` (lines 202–203)
- Modify: `tests/test_page_geometry.py` (append)

**Interfaces:**
- Consumes: `engine.geometry.at_rotation_zero` from Task 1; `build_page`, `block` and `exported` from Task 3.
- Produces:
  - no new engine names. `_erase_region` keeps its signature `(page, rect, fill) -> None`.
  - in `tests/test_page_geometry.py`: `CROPS`, `BLACK`, `_same_colour(actual, expected, tolerance=0.01)`, `_fills(page, colour)`, `_on(rect, target)`, `_inherited_rotation_page(rotate, cropbox=None) -> bytes`. Tasks 6 and 7 use them.

**Red/green reference, measured by the coordinator on the engine after Task 4.** "Fill on target" means the exported fill rectangle equals the target rect. The text is removed in every case, with or without the fix.

| CropBox | 0° | 90° | 180° | 270° |
|---|---|---|---|---|
| contained `[40 60 580 740]` | on target | **off** | **off** | **off** |
| oversized `[-40 -60 660 820]` | on target | on target | **off** | **off** |

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_page_geometry.py`:

```python
from engine.operations import _erase_region  # noqa: E402

GREEN = (0.0, 1.0, 0.0)
BLACK = (0.0, 0.0, 0.0)
CROPS = {"contained": "[40 60 580 740]", "oversized": "[-40 -60 660 820]"}


def _same_colour(actual, expected, tolerance=0.01):
    # Drawing colours come back as floats that have been through a content
    # stream, and a sampled fill is a 0-255 value divided by 255 (C11).
    return (
        actual is not None
        and len(actual) == len(expected)
        and all(abs(a - e) <= tolerance for a, e in zip(actual, expected))
    )


def _fills(page, colour):
    return [fitz.Rect(d["rect"]) for d in page.get_drawings() if _same_colour(d.get("fill"), colour)]


def _on(rect, target):
    return all(abs(a - b) < 1 for a, b in zip(rect, target))


@pytest.mark.parametrize("crop", sorted(CROPS))
@pytest.mark.parametrize("rotation", ROTATIONS)
def test_erase_region_paints_exactly_one_fill_on_the_target(rotation, crop):
    # R11. Every _clean_erase caller and redact_region go through
    # _erase_region, so this pins all of them. Three separate properties,
    # all checked on the exported bytes: the text is gone, there is exactly
    # one fill, and that fill is on the target -- checking only the first
    # is how this defect was missed.
    doc, handle = parse(build_page(rotation=rotation, cropbox=CROPS[crop]))
    target = fitz.Rect(block(doc, "LOW-MARKER").bbox)
    _erase_region(handle[0], target, fill=GREEN)
    page = exported(handle)[0]
    assert "LOW-MARKER" not in page.get_text()
    fills = _fills(page, GREEN)
    assert len(fills) == 1, f"expected one fill, got {fills}"
    assert _on(fills[0], target), f"fill painted at {tuple(fills[0])}, target was {tuple(target)}"
    assert handle[0].rotation == rotation


@pytest.mark.parametrize("rotation", ROTATIONS)
def test_redact_region_black_box_lands_on_the_target(rotation):
    doc, handle = parse(build_page(rotation=rotation, cropbox=CROPS["oversized"]))
    target = fitz.Rect(block(doc, "LOW-MARKER").bbox)
    redact_region(handle, 0, target)
    page = exported(handle)[0]
    fills = _fills(page, BLACK)
    assert "LOW-MARKER" not in page.get_text()
    assert len(fills) == 1 and _on(fills[0], target)


def _inherited_rotation_page(rotate, cropbox=None):
    """A page whose /Rotate is set only on its /Pages parent."""
    source = fitz.open()
    page = source.new_page(width=612, height=792)
    page.insert_text((72, 700), "LOW-MARKER", fontsize=12)
    if cropbox is not None:
        source.xref_set_key(page.xref, "CropBox", cropbox)
    parent = int(source.xref_get_key(page.xref, "Parent")[1].split()[0])
    source.xref_set_key(page.xref, "Rotate", "null")
    source.xref_set_key(parent, "Rotate", rotate)
    data = source.tobytes()
    source.close()
    return data


def test_redaction_on_an_inherited_rotation_lands_and_keeps_rotation():
    # Review Focus 3, with a contained CropBox so the fill-placement defect
    # is actually exercised (C4: without a crop this test was already green).
    # at_rotation_zero writes a page-level /Rotate while drawing and restores
    # it, so the page may end with an explicit value where it had an
    # inherited one -- the effective rotation must be unchanged.
    doc, handle = parse(_inherited_rotation_page("90", cropbox=CROPS["contained"]))
    assert handle[0].rotation == 90
    target = fitz.Rect(block(doc, "LOW-MARKER").bbox)
    redact_region(handle, 0, target)
    out = exported(handle)[0]
    fills = _fills(out, BLACK)
    assert out.rotation == 90
    assert len(fills) == 1 and _on(fills[0], target), f"fills {fills}, target {tuple(target)}"


@pytest.mark.parametrize("rotation", (90, 180, 270))
def test_both_redaction_calls_run_at_rotation_zero(rotation, monkeypatch):
    # R11 wraps BOTH calls. Only apply_redactions is known to need it, so
    # only a spy on each call can tell the wrapper was kept around both (C4).
    doc, handle = parse(build_page(rotation=rotation, cropbox=CROPS["contained"]))
    seen = {}
    real_add, real_apply = fitz.Page.add_redact_annot, fitz.Page.apply_redactions

    def spy_add(self, *args, **kwargs):
        seen["add_redact_annot"] = self.rotation
        return real_add(self, *args, **kwargs)

    def spy_apply(self, *args, **kwargs):
        seen["apply_redactions"] = self.rotation
        return real_apply(self, *args, **kwargs)

    monkeypatch.setattr(fitz.Page, "add_redact_annot", spy_add)
    monkeypatch.setattr(fitz.Page, "apply_redactions", spy_apply)
    redact_region(handle, 0, block(doc, "LOW-MARKER").bbox)
    assert seen == {"add_redact_annot": 0, "apply_redactions": 0}
    assert handle[0].rotation == rotation


@pytest.mark.parametrize("failing", ["add_redact_annot", "apply_redactions"])
def test_rotation_is_restored_when_a_redaction_call_raises(failing, monkeypatch):
    # A guard, green before and after the fix: it fails only if the restore
    # is not in a finally.
    doc, handle = parse(build_page(rotation=90, cropbox=CROPS["contained"]))

    def boom(self, *args, **kwargs):
        raise RuntimeError("injected")

    monkeypatch.setattr(fitz.Page, failing, boom)
    with pytest.raises(RuntimeError, match="injected"):
        redact_region(handle, 0, block(doc, "LOW-MARKER").bbox)
    assert handle[0].rotation == 90
```

- [ ] **Step 2: Run the tests and confirm they fail as the table predicts**

Run: `timeout 600 ./.venv/Scripts/python.exe -m pytest tests/test_page_geometry.py -v`

Expected — measured: **11 failed, 75 passed.**
- `test_erase_region_paints_exactly_one_fill_on_the_target`: exactly the five cells marked **off** in the table fail, with the "fill painted at" message.
- `test_redact_region_black_box_lands_on_the_target[180]` and `[270]` fail (the oversized row).
- `test_redaction_on_an_inherited_rotation_lands_and_keeps_rotation` fails on fill placement.
- `test_both_redaction_calls_run_at_rotation_zero[90]`, `[180]` and `[270]` fail: the spies see the page's own rotation.
- Already passing, and kept as guards: the on-target cells, black box at 0 and 90, and both `test_rotation_is_restored_when_a_redaction_call_raises` cases. The last pair fails only if the restore is not in a `finally`.

If a cell's result differs from the table, stop and report it. Do not delete the test.

- [ ] **Step 3: Implement the fix**

Add `at_rotation_zero` to the `engine.geometry` import in `engine/operations.py`.

In `_erase_region`, replace:

```python
    page.add_redact_annot(rect, fill=fill)
    page.apply_redactions(images=2, graphics=1, text=0)
```

with:

```python
    # Both calls at rotation 0 (spec R11): on a rotated page with a CropBox,
    # PyMuPDF removes the right text but paints the fill elsewhere -- ~88pt
    # away on the test pages, possibly over content that was NOT removed.
    # The rect stays in unrotated coordinates; only the page's orientation
    # changes, and at_rotation_zero restores it even if a call raises.
    with at_rotation_zero(page):
        page.add_redact_annot(rect, fill=fill)
        page.apply_redactions(images=2, graphics=1, text=0)
```

Keep the existing docstring. Add one line to it saying the pair runs at rotation 0 per R11.

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `timeout 600 ./.venv/Scripts/python.exe -m pytest tests/test_page_geometry.py -v`
Expected: 86 passed.

- [ ] **Step 5: Mutation check — the wrapper covers both calls**

Temporarily move `page.add_redact_annot(...)` out of the `with` block, above it. Expected: the three `test_both_redaction_calls_run_at_rotation_zero` cases fail on `add_redact_annot`. Restore it, and paste the failure line into your report.

- [ ] **Step 6: Run the full suite and commit**

Run: `timeout 600 ./.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: all pass.

```bash
git add engine/operations.py tests/test_page_geometry.py
git commit -m "fix: paint redaction and erase fills where the content was removed

On a rotated page with a CropBox, PyMuPDF removed the correct text but
painted the fill elsewhere -- 88pt away on the test pages, possibly over
content that was never removed. The privacy guarantee held; the visible
result did not. Both redaction calls now run at rotation 0, which lands the
fill on target at every rotation.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_016ns89haVgmSD9aXKkdw3Ka"
```

---

