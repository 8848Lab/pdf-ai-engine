# replace_text: widen before shrinking, keep the baseline (and C21) — Design Brief

**Status:** brief, pending critique. Once critiqued, a "REVISION after the
critique" section is appended with numbered rulings that are **binding over
the text below.**

## Intent

When a replacement is longer than the text it replaces, `replace_text` today
shrinks the font immediately, even when there is plenty of empty space to the
right. The owner approved the fix before Merge A (ledger, 2026-09-26):
**widen rightward into free space before shrinking, and keep the original
baseline.** The owner's live-test evidence: a form's Student Name value shrank
from 14.04pt to 8.29pt (0.9^5), and a paragraph line from 11.04pt to 8.05pt
(0.9^3).

The same small merge also takes C21, the parked edge-sampling fix from Merge A
(the owner chose to fold it in, 2026-09-28): background samples that fall off
the canvas are dropped instead of clamped onto the page edge.

## Verified facts (PyMuPDF 1.28.2, this repo at 81daa1c)

**V1. Every replace target is a single line.** `parse()` turns each span into
its own `TextBlock` (`engine/parser.py:68-79`), so a `TextBlock` never spans
more than one line.

**V2. Today a longer replacement wraps as well as shrinks, and its baseline
rises.** Probe `scratchpad/widen/probe1.py`, a form field with a box drawn to
x=400 and 194pt of empty box to the right of the value:
- `"Jo Lee"` (14pt, baseline y=100) replaced by `"Jonathan Lee"` exports as
  **two spans at 7.44pt**: `"Jonathan"` with its baseline at 92.95 and `"Lee"`
  with its baseline at 103.94. The second line's bbox reaches y=106.2, past the
  original bottom of 104.2 and onto the box's bottom border at 106.
  - The cause: `_insertion_rect`'s inflated height fits one line at full size
    but two lines at smaller sizes, and `insert_textbox` word-wraps.
- `"Alexandra Montgomery-Smith"` in the same field **fails** below the floor
  (7.44pt, then raises), **after** the old value has been erased.
- A paragraph line (11pt, baseline 315) replaced by a slightly longer line
  exports at **8.91pt with its baseline at 312.75**.

**V3. The baseline moves because `insert_textbox` pins the TOP of its box.**
Line 1's baseline sits at `rect.y0 + fontsize * ascender`, so every shrink step
raises the baseline.

**V4. `insert_text` at a point lands exactly, at every rotation.** Probe
`probe2.py`: `page.insert_text((100, 700), ...)` with no rotate or morph
arguments reads back with origin `(100, 700)` and `dir (1, 0)` at page
rotations 0, 90, 180 and 270. This holds together with Merge A's gate (the
text-drawing refusals still apply first).

**V5. `fitz.Font.text_length(text, fontsize)` gives the exact advance width.**
So whether a size fits can be decided **before** anything is erased. Today
that is only discovered after the erase (the "erased, then did not fit"
contract).

**V6. `page.get_drawings()` is cheap** (0.1ms on the probe page) and returns
vector items with their rects. A form field's box comes back as one `re`
item.

## Design

### W1. One line, drawn at the original baseline

The replacement is drawn with `page.insert_text` at the target's original
origin `(x0, baseline_y)`, as a single line. It never wraps.
- `TextBlock` gains an optional field `origin: tuple[float, float] | None =
  None`. The parser fills it from the span's `origin`. The default of `None`
  keeps every existing constructor valid.
- If `origin` is `None` (a caller-built `TextBlock`), the baseline is derived
  as `bbox.y0 + size * ascender` of the span's own font where it can be
  resolved, otherwise from the resolved font.

### W2. Available width, before any erase

The right limit `R` is the minimum of the following.

1. **The nearest obstacle to the right, within the target's vertical band**
   `[bbox.y0, bbox.y1]`, less a gap of `max(1pt, 0.25 * size)`. Obstacles are:
   - every other text span on the page whose bbox starts at or right of
     `target.x1` and overlaps the band;
   - every image bbox, under the same rule;
   - every vector drawing element whose extent overlaps the band and lies at
     or right of `target.x1`. Rectangles are decomposed into their four edges
     first, so a box's top and bottom borders, which start left of the target,
     are **not** obstacles, while its right border is.
2. **The column edge, when the target is a line of a paragraph.** Take the
   spans whose left edge aligns with the target's (within 2pt) and that lie
   within two line heights above or below. If any exist, the column edge is
   the maximum of their `x1` and the target's own `x1`. This stops a
   paragraph line growing past the column.
3. **The page's right margin:** `unrotated_bounds.x1 - left_margin`, where
   `left_margin` is the smallest text `x0` on the page minus `bounds.x0`,
   floored at 18pt. This assumes symmetric margins when nothing else bounds
   the text.

`R` is never less than the target's own right edge.

### W3. Size: widen first, then shrink exactly, and refuse before erasing

Let `w_avail = R - origin.x` and `w_need = text_length(new_text, size)` in the
resolved font.
- If `w_need <= w_avail`, draw at the **original size**.
- Otherwise the size is `size * w_avail / w_need`. That is exact: the
  existing 0.9-step loop is not used, because the advance width is linear in
  the font size.
- If that size is below the 50% floor (`_SHRINK_FLOOR_RATIO`, unchanged),
  raise **before erasing**, so the document is untouched. This retires the
  "erased, then did not fit" failure for `replace_text`.

A draw that raises after the erase is still possible and stays a plain
`ValueError`, as Merge B's B1 guard test requires.

### W4. Erase region unchanged

The erase stays the target's own bbox plus the precision pad. The widened
area was free by construction (W2), so there is no old ink there to remove.
Background sampling surrounds the erased rect, as today.

### W5. Non-horizontal text keeps today's behaviour

Some spans have a writing direction other than `(1, 0)`: vertical text, or
text under a rotated content `cm` (Merge A's final review measured such
cases).
- `TextBlock` gains `direction: tuple[float, float] | None = None`, filled
  by the parser from the line's `dir`.
- For any direction other than `(1, 0)`, `replace_text` keeps its current
  box-and-shrink path, unchanged.

### W6. Scope

Only `replace_text` changes.
- `move_block`'s destination draw keeps `_draw_shrink_to_fit`. The same text
  at the same size fits its own width.
- `insert_block` keeps wrapping inside its caller-given box.
- The `/UserUnit`, rotation and overhang gates are unchanged, and still run
  first.

### W7. C21, off-canvas background samples

In `_sample_background_color`, each sample records whether it fell on the
canvas before clamping. When at least one sample is on the canvas and at
least one is off it, the median is taken over the on-canvas samples only.
When none is on the canvas, the clamped set is used as today. This is the
Merge A final reviewer's patch. It passed the suite then, and there is no
known wrong-colour case today (728/728); this is defence in depth for rects
that straddle the page edge.

## Contracts that must not change

- Every existing test passes **unedited**. If one depended on the wrapping
  behaviour in V2, that test is recorded and the owner decides; it is not
  edited silently.
- `replace_text`'s signature.
- The Merge A gate order, and Merge B's `RefusedBeforeMutation` semantics.
  The new "does not fit even at the floor" refusal happens before any
  mutation, so it raises `RefusedBeforeMutation`.
- The erase never reaches the next line (the existing "erase keeps the
  original height" rule).

## Testing (red first)

- **The form field (V2):** a longer value fits at its original size inside
  the box, **on the original baseline**, as **one span**, on the exported
  bytes. The very long value is refused **before erasing** (fingerprint
  unchanged).
- **Obstacles:** a text span, an image, a vertical rule and a box's right
  border each stop the widening at their left edge minus the gap. A box's
  top and bottom borders do not.
- **The paragraph line:** it widens only to the column edge, then shrinks
  exactly. Its baseline is unchanged.
- **All four rotations and Merge A's crop geometries:** the replacement lands
  at the original origin.
- **Non-horizontal text:** the path is unchanged. A test pins today's
  behaviour.
- **C21:** a rect straddling the page edge samples the background, not a
  glyph, when the clamped sample would land on ink. This needs a fixture
  where it matters. If one cannot be built, the test pins that on-canvas
  samples are preferred.
- **Mutation gate:** revert each of W1, W2 (per obstacle kind, plus the
  column and the margin), W3 (widen, the exact shrink, the refusal before
  erasing) and W7 in turn. A named test must fail for each.

## Review tiering

Opus for routine tasks. Fable for the final review, because the erase and
redraw touch privacy-adjacent output: a widened draw must never cover
neighbouring content.

## Out of scope

- Reflowing onto multiple lines, or moving neighbouring content.
- Right-to-left or right-aligned text. The widening grows to the right from
  a left origin only. A right-aligned value would move its right edge, and
  that is noted as a known limitation for the critique to weigh.
- `move_block` and `insert_block`.

---

## REVISION after the critique

**Binding over everything above.** The critic was a Fable reviewer, standing in
for the owner's usual Codex critique, which is unavailable in the cloud
session. Its verdict was **REVISE BRIEF**. Every point was executed, and the
probes and their outputs are in
`docs/superpowers/records/2026-09-28-replace-text-widen/probes/critique/`.

The core design is confirmed. With it, the owner's form value draws at 14pt
as one span on baseline 100.0. The paragraph line draws at 9.91pt on its
unchanged baseline 315.0; today it draws at 8.91pt, at 312.75.

### Owner's decisions (2026-09-28)

- **D1: the five contract tests are updated, not kept.** These five tests pin
  today's "erase, then raise if it does not fit" contract, or an
  `insert_textbox` spy:
  - `test_replace_text_raises_when_text_does_not_fit_even_shrunk`
  - `test_replace_text_reports_an_unexpected_drawing_failure_as_a_valueerror`
  - `test_refused_before_mutation_is_raised_exactly_when_nothing_changed[replace draw raises]`
  - `test_a_failed_replace_leaves_state_consistent_with_the_real_document`
  - `test_a_failure_after_a_mutation_still_refreshes_the_ids`

  Each is rewritten to assert the new contract: refused before any erase,
  fingerprint unchanged. The last one needs a different post-mutation failure
  to exercise. Every edit is listed in the ledger with its before and after,
  and reviewers check each one. With R9, the two spy tests may need no edit;
  only the edits that are actually needed are made.
- **D2: a line break in `new_text` collapses to a single space.** This covers
  `\r\n`, `\n` and `\r`, plus U+2028 and U+2029. W1 draws one line by
  definition. The existing newline test passes unedited.
- **D3: text colour is preserved.** `TextBlock` gains `color`, filled from
  the span, and the replacement is drawn in it. Today every replacement comes
  back black.

### Rulings (coordinator, adopting the critique's proposals)

**R1: a baseline sanity gate.**
- Use the span origin only when both of these hold:
  - `|origin.y - (bbox.y0 + size*asc)| <= 1pt`
  - `|bbox.height - size*(asc - desc)| <= 1pt`
- Here `asc` and `desc` are the span's own reported metrics.
- Otherwise, and whenever `origin` is None, take today's box path. That path
  is unchanged except for D2 and D3.
- This single check covers y-mirrored text (which reports `dir` (1,0)),
  scaled `Tm` and `Tz`, Type3 fonts and ZapfDingbats. The derived-baseline
  fallback from W1 is withdrawn.

**R2: see D2.**

**R3: an obstacle is anything whose x1 is greater than `target.x1`.**
- A span, image, drawing segment, widget or annotation counts as an obstacle
  when it overlaps the band and its `x1 > target.x1`, wherever it starts.
- Its limit is `max(item.x0, target.x1) - gap`.
- So a neighbour that overlaps the target's own x-range gives no widening.
  The critic measured a label's widened draw covering a neighbour whose bbox
  started 1.5pt left of the target's x1; this rule prevents that.

**R4: widgets and annotations are obstacles.** Every `page.widgets()` rect
and every `page.annots()` rect counts, including empty fields, which neither
`get_text` nor `get_drawings` reports.

**R5: an image in the band means no widening.** If an image overlaps the band
with `x1 > target.x1`, wherever it starts, then R is the target's own x1. Its
printed ink is invisible to the obstacle model. This is what keeps widening
off scanned pages.

**R6: horizontal rules.**
- A segment under 1pt tall is never an obstacle.
- A horizontal rule that overlaps the target's x-range and lies within
  `[baseline, bbox.y1 + 2pt]` bounds R at its own x1, so the text stays
  within its underline.
- Dotted or dashed leaders that stop widening are accepted as a known
  limitation and pinned by a test. That outcome is safe: today's shrink
  applies.

**R7: the column edge applies only to paragraphs.**
- Rule 2 applies only when **at least two** aligned neighbours lie within the
  window and their x1 values agree within 10% of the column width.
- A single aligned neighbour, such as a heading over a line or a stacked form
  field, does not cap widening.
- A red test uses a stacked-form fixture at a 22pt pitch. That is the owner's
  live shape, and it shrinks to 9pt without this ruling.

**R8: right-aligned values do not widen.** A neighbour within two line
heights whose x1 is within 1pt of the target's, while its x0 differs by more
than 2pt, marks the target as right-aligned. Then R is the target's own x1,
and the text shrinks as today.

**R9: `insert_textbox` stays the drawing primitive.**
- The rect is `(origin.x, origin.y - size*asc, origin.x + w_need + pad,
  origin.y - size*desc + slack)`.
- It holds exactly one line by construction and pins the baseline, and the
  two spy tests keep working.
- The plan must verify with a test that nothing wraps: the result is one
  span, and its baseline equals the original.
- If `insert_textbox` cannot meet that exactly, `insert_text` is used and
  the spy tests fall under D1.

**R10: see D1.** The contract "every existing test passes unedited" is
replaced by D1's ledgered edits.

**R11: an amendment to ruling B1.**
- `replace_text`'s new "does not fit even at the floor" check runs before any
  mutation, so it raises `RefusedBeforeMutation`.
- For `replace_text` alone, the "erased, then did not fit" failure is
  retired.
- A draw that raises after the erase stays a plain `ValueError`.
- Tests use `fingerprint()`, never `export()` bytes, which differ from run to
  run.

**R12: see D3.**

**R13: direction tolerance.**
- `dir` is compared to (1,0) with a tolerance of 1e-3.
- A near-horizontal OCR skew (1° gives (1.0, -0.017)) takes today's path. That
  is stated here and pinned by a test.

**R14: the C21 fixture.**
- The red test is the critic's page-frame corner fixture: `probe_w7.py`,
  cases 7 and 8.
- On the old sampler that fixture reads grey (0.498) or wrong-blue.
- With C21 it reads the true colour.

**R15: scope notes.**
- W3's exact formula assumes an unscaled text matrix. R1 routes scaled text
  to today's path.
- Originals drawn with `Tc`, `Tw` or `TJ` kerning are narrower when redrawn,
  just as today.
- Right-to-left runs report `dir` (1,0) with their origin at the right, so
  W1 would draw them wrongly. Treat them as out of scope, and name the
  limitation in the README.
- `text_length` overestimates embedded TrueType fonts by up to 0.13pt. That
  errs on the safe side.

### Corrections to the brief

- The suite has 733 tests, not the 728 the brief cited from Merge A.
- V5 holds exactly for Base-14 fonts only; see R15.
- W2's claim that the widened area is "free by construction" was false for
  image ink and for overlapping neighbours. It now holds because of R3–R5.
- W5's claim that anything other than (1,0) is diverted missed y-mirrored
  text. R1 covers that.
