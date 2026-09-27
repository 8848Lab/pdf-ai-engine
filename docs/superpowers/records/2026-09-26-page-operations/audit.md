# Task 8: R9 audit and regression record

Platform: Linux (vm 6.18.44-fc-v42), PyMuPDF 1.28.2, `.venv/bin/python`.

## 1. Drawing calls

Search commands run:

```bash
grep -n "insert_textbox\|insert_text(\|insert_image\|draw_rect\|draw_line\|add_redact_annot\|apply_redactions\|show_pdf_page" engine/*.py
```

No `draw_rect`, `draw_line`, `insert_text(` or `show_pdf_page` call exists anywhere in `engine/` (R14 confirmed: there is no unhandled drawing primitive). Every hit that is an actual PyMuPDF drawing call, not a comment/docstring mention:

| Call site | Call | Reached by (operation → its gate) | Handling |
|---|---|---|---|
| `engine/operations.py:231` (`_erase_region`) | `page.add_redact_annot(rect, fill=fill)` | `redact_region` (op body `operations.py:570`) → gated `operations.py:569` (`OTHER_DRAWING`); `_clean_erase` → `replace_text` (`operations.py:711`) → gated `operations.py:654` (`TEXT_DRAWING`); `_clean_erase` → `delete_block` (`operations.py:737`) → gated `operations.py:736` (`OTHER_DRAWING`); `_clean_erase` → `move_block` source erase (`operations.py:833`) → gated `operations.py:792` (`OTHER_DRAWING`); `_clean_erase` → `replace_image` (`operations.py:1030`) → gated `operations.py:996` (`OTHER_DRAWING`) | Rotation 0 (R11): wrapped in `at_rotation_zero` (`operations.py:230`). Every caller runs `_refuse_unsupported_drawing` (→ `geometry.drawing_refusal`) before this, per the "reached by" column. |
| `engine/operations.py:232` (`_erase_region`) | `page.apply_redactions(images=2, graphics=1, text=0)` | Same call graph and gates as the row above (same `with at_rotation_zero` block). | Rotation 0 (R11), same gates as above. |
| `engine/operations.py:438` (`_draw_shrink_to_fit`) | `page.insert_textbox(insert_rect, text, fontname=..., fontsize=..., color=(0,0,0))` | `replace_text` (`operations.py:717`) → gated `operations.py:654` (`TEXT_DRAWING`); `move_block` destination draw (`operations.py:834`) → gated `operations.py:810` (`TEXT_DRAWING`, on `dest_index`) | Text drawing, gated by the overhang rule (R5, rule 5 of `drawing_refusal`) and the invalid-rotation, inconsistent-boxes, `/UserUnit` and 2^18-bound rules (rules 1-4), all via the `TEXT_DRAWING` kind. |
| `engine/operations.py:932` (`insert_block`) | `page.insert_textbox(insert_rect, text, fontname=..., fontsize=..., color=(0,0,0))` | `insert_block` (`operations.py:888` gate) | Text drawing, gated exactly as above (`TEXT_DRAWING`). |
| `engine/operations.py:1036` (`replace_image`) | `page.insert_image(rect, stream=new_image_bytes, keep_proportion=True)` | `replace_image` (`operations.py:996` gate, `OTHER_DRAWING`) | Rotation 0 (R4): wrapped in `at_rotation_zero` (`operations.py:1035`). Not subject to the text-only overhang rule (rule 5 exempts `OTHER_DRAWING`). |
| `engine/operations.py:429` (`_draw_shrink_to_fit`) | `page.insert_font(fontname=resolved_fontname, fontbuffer=resolved_font.buffer)` | Same callers as the `insert_textbox` row above (`replace_text`, `move_block` destination) | Not position-dependent: registers a font resource on the page, draws nothing at a coordinate. Still runs only after the caller's gate, since it executes inside the same function. |
| `engine/operations.py:931` (`insert_block`) | `page.insert_font(fontname=resolved_fontname, fontbuffer=resolved_font.buffer)` | `insert_block` (`operations.py:888` gate, `TEXT_DRAWING`) | Not position-dependent: registers a font resource on the page, draws nothing at a coordinate. Runs after the gate at line 888, in the same function body. |

Gate inventory (Task 7, `_refuse_unsupported_drawing` → `geometry.drawing_refusal`) — 7 call sites, confirmed against `progress.md` ("T7... covers 7 call sites, including both of `move_block`'s"):

| Gate site | Operation | Kind |
|---|---|---|
| `operations.py:569` | `redact_region` | `OTHER_DRAWING` |
| `operations.py:654` | `replace_text` | `TEXT_DRAWING` |
| `operations.py:736` | `delete_block` | `OTHER_DRAWING` |
| `operations.py:792` | `move_block` (source) | `OTHER_DRAWING` |
| `operations.py:810` | `move_block` (destination) | `TEXT_DRAWING` |
| `operations.py:888` | `insert_block` | `TEXT_DRAWING` |
| `operations.py:996` | `replace_image` | `OTHER_DRAWING` |

**Private-API row (REVISION 2, ruling C16).** `geometry.page_transform` (`engine/geometry.py:129-142`) depends on `page._pdf_page()` and `mupdf.pdf_page_transform`, neither of which is public PyMuPDF API. Both fail closed: `page_transform` catches `AttributeError`/`TypeError` and returns `None`, which `layout_orientation` turns into `None`, which `drawing_refusal`'s rule 2 turns into a refusal of every drawing operation on every page. A PyMuPDF upgrade that removes this binding therefore refuses everything rather than drawing something wrongly (ledger ruling C16: "the private-API dependency could break on a PyMuPDF upgrade. It fails closed... so it cannot fail silently"). Any other exception from the binding propagates out of `drawing_refusal` before any mutation (callers should treat it as a refusal: parked as ruling C17); if `pymupdf.mupdf` itself disappears, `engine.geometry` fails to import. In the `None` case the operator sees the "lays out inconsistently" message on every page.

## 2. Dimension consumers

Search command run:

```bash
grep -rn "page\.rect\|\.rect\.width\|\.rect\.height\|\.width\b\|\.height\b\|mediabox\|cropbox" engine/ webui/ --include=*.py
```

| File:line | What | Used for coordinate math? |
|---|---|---|
| `engine/geometry.py` (throughout) | `page.rect`, `page.mediabox`, `page.cropbox` inside `unrotated_bounds`, `to_display_matrix`, `visible_area`, `crop_origin_overhangs`, `drawing_refusal` | **Yes** — this module is the single place that does the coordinate math; every other consumer either reuses these functions or is display-only. |
| `engine/parser.py:109-110` | `pdf_page.rect.width`, `pdf_page.rect.height` stored on the parsed `Page` | No — display-only, confirmed. Now documented with a comment (Step 2, at lines 106-108) pointing at `unrotated_bounds` for anyone tempted to use it for math. |
| `webui/session.py:290` (`get_pages_summary`) | `handle[i].rect.width`, `handle[i].rect.height` | No — display-only, confirmed (returned to the UI as page dimensions, never fed back into an operation call). |
| `webui/session.py:277-278` (`get_images_summary`) | `entry["image"].width`, `entry["image"].height` | No — but this is a different object than the coordinator's claim covers: it is `Image.width/height`, the *raster* pixel dimensions of an image placement (from `engine/document.py`'s `Image` dataclass), not a page dimension at all. Display-only, but not one of the two items the coordinator named. |
| `engine/operations.py:280-281` (`_sample_background_color`) | `pixmap.width - 1`, `pixmap.height - 1`, used to clamp a sample point into pixel-index range | **Correction to the coordinator's claim.** This IS used for coordinate math — it clamps a display-space point (produced by `to_display_matrix`, which is rotation/CropBox/UserUnit-aware) into the bounds of `page.get_pixmap()`'s own raster. It is the pixmap's dimensions, not `page.rect`, and it is already routed through the geometry module's display matrix, so it is correct, but it is a coordinate-math consumer the coordinator's "only `parser.py` and `get_pages_summary`" claim did not list. |
| `engine/operations.py:355,693` (comments) | `rect.height` mentioned in prose | N/A — comments, not code. |

**Correction to the coordinator's display-only claim:** `engine/operations.py:280-281` (`_sample_background_color`'s pixmap clamping) is a coordinate-math consumer, not display-only, though it is on a `Pixmap` object rather than `page.rect` and is unaffected by the geometry rules because it already runs downstream of `to_display_matrix`. `webui/session.py:277-278` is an additional display-only hit the coordinator's grep summary omitted (it is `Image.width/height`, not a page dimension).

## 3. Regression record

### 1. The critic's probes (PyMuPDF baseline)

`recheck_geometry.py` exercises its own helper copies (in `recheck_common.py`), not `engine.geometry` — a baseline of what PyMuPDF itself does, kept per ruling C10 ("it stays as a PyMuPDF baseline. Task 8 adds a production run that imports `engine.geometry`").

Run (Linux, PyMuPDF 1.28.2, `.venv/bin/python`; path adjusted per coordinator correction 2 — no Windows-only paths were present in the committed script itself, so it was run unmodified from the probes directory):

```bash
cd docs/superpowers/records/2026-09-26-page-operations/probes
timeout 600 ../../../../../.venv/bin/python recheck_geometry.py | tail -1
```

Actual output:

```
SUMMARY {'cases': 1024, 'bounds_fail': 0, 'visible_fail': 0, 'offpage_fail': 0, 'sample_fail': 0, 'library_sample_fail': 640, 'matrix_different': 732}
```

This matches the brief's expected line exactly; no investigation needed.

### 2. The production run (engine.geometry itself)

```
$ .venv/bin/python -c "import engine.geometry as g; print(g.__file__)"
/home/user/pdf-ai-engine/engine/geometry.py
```

The printed path is inside this checkout, as required.

```
$ .venv/bin/python -m pytest tests/test_geometry.py -q
136 passed in 18.26s
```

### 3. The Task 2 mutation, stated accurately

Re-executed at HEAD: replacing the body of `crop_origin_overhangs` (`engine/geometry.py:170`) with `return not page.mediabox.contains(page.cropbox)` gives **12 failed, 502 passed**. In `tests/test_geometry.py` 5 fail: `test_crop_origin_overhangs_matches_where_text_actually_drifts[bottom]`, `[right]`, `[negative-origin-mediabox]`, `test_the_predicate_matches_observed_text_drift_on_all_256_unit_one_cases` (60 mismatches) and `test_the_matrix_agrees_with_pymupdfs_own_drawing` (60 mismatches). In `tests/test_page_geometry.py` 7 fail: `test_text_operations_refuse_exactly_the_overhang_pages` for bottom and right under each of `replace_text`, `move_block` and `insert_block`, plus `test_text_operations_are_allowed_on_a_negative_origin_mediabox`.

Historical note: at Task 2 the same mutation failed 4 tests (the three parametrised ids plus the 256-case drift test); the other 8 tests were added in Tasks 2-7.

The change was made in a working copy, the full suite was run to confirm the 12/502 split above, and the file was then restored from a backup taken before the edit; `git diff` on `engine/geometry.py` is empty after the restore, confirming no engine change survived.

### 4. Timings

Any timing figure elsewhere in this plan (e.g. "about 4 seconds" for the matrix) was measured on the coordinator's machine and is not a requirement. This session's own probe run was timed directly: `recheck_geometry.py`'s 1,024-case matrix took **6.858s** wall-clock on this container (`time` around the `python recheck_geometry.py` invocation), well under the 600s timeout.

## 4. Full suite

```
$ .venv/bin/python -m pytest tests/ -q
........................................................................ [ 14%]
........................................................................ [ 28%]
........................................................................ [ 42%]
........................................................................ [ 56%]
........................................................................ [ 70%]
........................................................................ [ 84%]
........................................................................ [ 98%]
..........                                                               [100%]
514 passed in 22.03s
exit 0
```
