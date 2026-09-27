### Task 8: Audit, documentation, and the regression record

**Files:**
- Create: `docs/superpowers/records/2026-09-26-page-operations/audit.md`
- Modify: `engine/parser.py` (the docstring near line 106)
- Modify: `README.md`, under `## Operations`
- Modify: `docs/superpowers/specs/2026-09-26-page-operations-design.md` (two wording corrections)

**Interfaces:**
- Consumes: everything above.
- Produces: no code.

- [ ] **Step 1: Carry out the R9 audit and write it down**

Search `engine/` for every drawing call and every use of page dimensions:

```bash
grep -n "insert_textbox\|insert_text(\|insert_image\|draw_rect\|draw_line\|add_redact_annot\|apply_redactions\|show_pdf_page" engine/*.py
grep -rn "page\.rect\|\.rect\.width\|\.rect\.height\|\.width\b\|\.height\b\|mediabox\|cropbox" engine/ webui/ --include=*.py
```

Create `audit.md` with two tables:

1. **Drawing calls.** Every hit, with its file:line, and how it is now handled. Each call is either:
   - at rotation 0 (R4 / R11); or
   - text drawing, gated by the overhang and `/UserUnit` rules; or
   - not position-dependent, such as `insert_font`, with the reason.

   Confirm there is no `draw_rect` or other drawing primitive left unhandled (R14).
2. **Dimension consumers.** Every use of page dimensions in `engine/` and `webui/`. For each, say whether it is used for coordinate math. The coordinator's grep found only `parser.py`'s `Page.width/height` and `session.get_pages_summary()`, both of which are display-only. Confirm or correct that.

- [ ] **Step 2: Document the display dimensions in the parser**

In `engine/parser.py`, add a short comment above the `width=pdf_page.rect.width,` line:

```python
                # DISPLAY dimensions: page.rect, which swaps width and height at
                # 90/270. Block bboxes are in UNROTATED space -- use
                # engine.geometry.unrotated_bounds for any coordinate math.
```

- [ ] **Step 3: Document supported page geometry in the README**

Add this paragraph at the end of the `## Operations` list in `README.md`:

```markdown
**Page geometry.** Every operation is correct on rotated pages, on pages with
a CropBox, and on fractional-size pages. The refusal check decides from the
layout PyMuPDF itself computes for the page (its own page transform and
boxes), never from the raw PDF keys, so it agrees with what gets drawn. These
configurations are refused before anything is changed, with a message that
says why:
- an invalid rotation: a `/Rotate` that is not a multiple of 90, or a negative
  `/UserUnit`, which lays the page out at a different orientation;
- page boxes PyMuPDF lays out inconsistently (malformed, or under 1pt);
- `/UserUnit` scaling (support is planned);
- page boxes beyond 2^24 points, where coordinates lose precision;
- for the three text-drawing operations only, a CropBox whose top-left extends
  past the MediaBox.

Redaction is not refused because of a CropBox overhang alone. The check reads
MuPDF's page transform through PyMuPDF's low-level binding; if a PyMuPDF
upgrade removes it, every page is refused rather than drawn wrongly. See
`docs/superpowers/specs/2026-09-26-page-operations-design.md`.
```

- [ ] **Step 4: Correct the spec's record of the false positives**

In `docs/superpowers/specs/2026-09-26-page-operations-design.md`, replace:

```markdown
gives false positives on two documents that behave correctly: a right-only overhang,
and a MediaBox with a negative origin (`[-100 -100 512 692]`). It would refuse valid,
real documents.
```

with:

```markdown
gives false positives on three documents that behave correctly: a right-only overhang,
a bottom-only overhang (raw CropBox `[0 -60 612 792]`, which PyMuPDF reports as
`(0, 0, 612, 852)` against a MediaBox of `(0, 0, 612, 792)`), and a MediaBox with a
negative origin (`[-100 -100 512 692]`). It would refuse valid, real documents.
(Corrected during Merge A: Task 2's mutation check found the third.)
```

- [ ] **Step 5: Record the regression evidence**

Add a section to `audit.md` named "Regression record", containing:

1. **The critic's probes.** They are a PyMuPDF baseline: `recheck_geometry.py` exercises its own helper copies, not the engine.

   ```bash
   cd docs/superpowers/records/2026-09-26-page-operations/probes
   timeout 600 ../../../../../.venv/Scripts/python.exe recheck_geometry.py | tail -1
   ```

   Expected: `SUMMARY {'cases': 1024, 'bounds_fail': 0, 'visible_fail': 0, 'offpage_fail': 0, 'sample_fail': 0, 'library_sample_fail': 640, 'matrix_different': 732}`.

2. **The production run.** This is the same 1,024-case matrix, run through `engine.geometry` itself, with the module's location recorded:

   ```bash
   timeout 600 ./.venv/Scripts/python.exe -c "import engine.geometry as g; print(g.__file__)"
   timeout 600 ./.venv/Scripts/python.exe -m pytest tests/test_geometry.py -q
   ```

   The printed path must be inside this checkout. Paste it and the pytest summary line.

3. **The Task 2 mutation, stated accurately.** Replacing `crop_origin_overhangs` with `mediabox.contains(cropbox)` fails **4** tests: the bottom, right and negative-origin cases, plus the 256-case drift test (60 mismatches).

4. **Timings.** Any timing in this plan, such as "about 4 seconds" for the matrix, was measured on the coordinator's machine and is not a requirement.

- [ ] **Step 6: Run the full suite and commit**

Run: `timeout 600 ./.venv/Scripts/python.exe -m pytest tests/ -q > "$TEMP/task8-pytest.txt" 2>&1; echo "exit $?"`

Expected: exit 0, all pass. Record the final count and the exit status in `audit.md`, and put the full output file's contents in your report.

```bash
git add docs/superpowers/records/2026-09-26-page-operations/audit.md engine/parser.py README.md docs/superpowers/specs/2026-09-26-page-operations-design.md
git commit -m "docs: audit page geometry handling and document supported configurations

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_016ns89haVgmSD9aXKkdw3Ka"
```

---

## REVISION 2: the Task 2 gate design changed (rulings C15, C16)

Task 2's security re-reviews found that raw-key parsing could not keep up with MuPDF's own parser. The gate now reads PyMuPDF's interpreted geometry (C15) and MuPDF's real page transform (C16). The ledger records each bypass and the coordinator's verification: the 1,024-case matrix and 128 adversarial PDFs, compared against a drawing probe.

Consequences for the tasks above:
- **Task 7.** Its tests match the new messages. The "invalid rotation", "/UserUnit", "Support is planned", "nothing was changed" and "CropBox" phrases were all kept. No text change.
- **Task 8.** The README paragraph was updated above to describe the new refusal classes. The audit should add one row for the private-API dependency: `page._pdf_page()` plus `mupdf.pdf_page_transform`, which fail closed.
