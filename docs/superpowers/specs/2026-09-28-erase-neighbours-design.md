# Erasing a block must not delete its neighbours (P2, with P1) — Design Brief

**Status:** brief, awaiting critique. When the critique is done, a "REVISION after the
critique" section will be appended. Its numbered rulings are **binding over the text
below.**

## Intent

This is the owner's most serious parked item, P2 from the widen merge's final review.
At tight line spacing, `delete_block`, `replace_text` or `move_block` on one line
**silently deletes the whole of the line above and the line below.** The same merge
also takes P1: erasing a form value whose font is taller than the box notches the box's
top border.

## Verified facts (PyMuPDF 1.28.2, master f881d95)

The probes are in `docs/superpowers/records/2026-09-28-erase-neighbours/probes/`.

**E1. When MuPDF removes a character.**
`apply_redactions(text=0)` removes a character when the redaction rect overlaps more
than **10% of the character's bbox**. Evidence from `thresh.py`:
- 12pt text is removed once the vertical overlap passes 1.649pt of its 16.488pt height;
  at 24pt the threshold is 3.298pt of 32.976pt. Both are a ratio of exactly 0.100.
- Horizontally, the same rule removed a 2pt sliver of the "W" in "WORD".

**E2. Neighbouring lines' bboxes overlap at ordinary tight leading.**
A span's bbox is `size * (ascender - descender)` tall, which is about 1.37× the font
size for Helvetica. So at a line pitch below roughly 1.37× the size, the boxes of
adjacent lines overlap, and past 10% of the height the neighbours are removed. Evidence
from `rule.py`, 12pt Helvetica, three lines, erasing the middle one's own bbox:
- at pitch 18, 16.5 and 15, both neighbours survive;
- at pitch **14.4** (a common 1.2× leading), 13 and 12, **both neighbours are deleted
  entirely.**

**E3. Clipping the erase rect at the neighbours' bbox edges fixes it for vector
text.** `clip.py` erases `[max(bbox.y0, above.y1), min(bbox.y1, below.y0)]` with
`images=2, graphics=1, text=0`. At pitches 14.4, 13, 12 and 11, the target is removed
and both neighbours survive, even with only 33% of the target's height left inside the
rect. The characters go whole, because redaction removes glyph objects rather than
clipping them. So none of the target's ink is left behind in the clipped-off strips.

**E4. The erase's other duties.**
- `images=2` blanks the pixels of any overlapping image.
- The fill paints over the rect.
- On a **scanned page**, the target's printed ink is in the image, not in the text
  layer. So a clipped rect would leave slivers of the target's printed ascenders and
  descenders in the strips it no longer covers.
- The unclipped rect, conversely, blanks slivers of the **neighbours'** printed ink,
  and deletes the neighbours' invisible OCR words from the text layer. That last part
  is P2 again, silently, on scans.

**E5. P1's mechanism.**
- `graphics=1` removes only graphics *contained* in the rect. A form box whose top
  border crosses the rect is kept.
- The fill, though, paints a white band over the border segment inside the rect. That
  is the notch.
- On the owner's form the 14pt value's bbox (y0 84.95) reaches above the border at
  y=86.

## Design

**N1. Neighbour-aware vertical clip, for the text-erasing operations only.**

`delete_block`, `replace_text` (both its paths), and `move_block`'s source erase work
out their erase rect vertically as follows.
- Start from today's rect (the target bbox plus the precision pad).
- Take every other text span whose bbox overlaps the rect horizontally and overlaps it
  vertically:
  - if it lies above the target's centre line, raise `y0` to its `y1`;
  - if it lies below, lower `y1` to its `y0`.
- Same-line neighbours are left to today's horizontal pad rule.
- If the clipped rect keeps less than **15%** of the target's own bbox height, raise
  `RefusedBeforeMutation` ("lines overlap too closely to erase this one without
  damaging its neighbours; nothing was changed") **before** anything is mutated.
  15% sits safely above E1's 10% removal threshold.
- `redact_region` is **unchanged**. A redaction removes everything its caller's rect
  overlaps, which is privacy-first by design.

**N2. Drawn horizontal rules crossing the rect edge (P1).** A drawn horizontal segment
(a rule, or a box's top or bottom edge) that
- crosses the rect vertically within its top or bottom 15%, and
- extends horizontally beyond the target on both sides, or starts left of it,

clips the rect the same way, to stop just short of the rule's stroke. The same 15%
floor and refusal apply. Such a rule belongs to the layout, not to the target.

**N3. Scanned (image-backed) targets.** When an image overlaps the target's band, the
text layer is OCR, the target's ink is in the image, and N1's clip trades one defect
for another (E4). Two options are left for the critique:
- **(a)** Keep today's full rect on image-backed targets. The neighbours' OCR words
  and ink slivers are still lost there, as today.
- **(b)** Clip the text removal (N1) but blank the image pixels over the full rect, as
  two redactions. The first uses the clipped rect with `text=0`. The second uses the
  full rect with `text=1` (keep text), `images=2`, `graphics=0` and the fill. This
  removes the target's printed ink fully and keeps the neighbours' OCR text, but it
  still whitens slivers of the neighbours' printed ink in the overlap strips.

The brief leans to **(b)**, because silently losing OCR words is the worse defect;
the critique is to measure both.

**N4. Background sampling** keeps sampling around the rect actually filled.

## Contracts

- Every existing test passes unedited. If a test depends on neighbour deletion, it is
  recorded and the owner decides.
- `redact_region`'s behaviour is unchanged.
- The new refusal happens before any mutation (`RefusedBeforeMutation`), in line with
  Merge B's B1 and the widen merge's R11.

## Testing (red first)

- Three-line paragraphs at pitches 18 → 11. Delete, replace (widen path and box path)
  and move the middle line. The neighbours survive in the **exported** text and pixels;
  the target is gone.
- The first and last lines of a paragraph, where only one side is clipped.
- The refusal when the lines overlap past the floor, with the fingerprint unchanged.
- P1: the owner's form value is replaced or deleted and the box border is unbroken, by
  pixel diff.
- Scanned pages (both N3 options measured). Use `sandwich.pdf` and a synthetic scan
  with an OCR layer at tight leading.
- The mutation gate: revert N1 (above and below separately), the 15% floor, N2 and N3,
  and a named test must fail for each.

## Out of scope

- `redact_region`'s over-removal. It is deliberate and privacy-first; a later
  "precise redaction" option could revisit it.
- P4, the redaction fill bleeding about 0.5pt: this merge can re-measure it, but not
  fix it.

---

## REVISION after the critique

**Binding over everything above.** The critic was a Fable reviewer, standing in for Codex, and returned **REVISE BRIEF**. Every point was executed. The probes and their outputs are in `docs/superpowers/records/2026-09-28-erase-neighbours/probes/critique/`.

The direction holds. With the same-line rule in R2, a prototype passes all 868 existing tests. On paragraphs at 1.0–1.6 leading, mixed sizes, drop caps, tables, two columns, rotated pages and cropped pages, the neighbours stay intact with 0 pixels damaged and 0 target ink left behind. No owner decision is needed: no existing test is edited.

### Rulings (coordinator, adopting the critique)

**R1: E1, restated.**
- MuPDF removes a glyph when the redaction rect intersects the glyph's line box, inset by 10% on each edge. The line box runs from the font's ascender to its descender and spans the glyph's advance width.
- It is not area-based, and it applies on both axes independently.
- Consequences:
  - A two-sided clipped band of any positive height removes the target.
  - A one-sided band, on a first or last line, must exceed 10% of the target's height.

**R2: same-line exclusion.**
- A span is a same-line neighbour, excluded from the vertical clip, if and only if `|span.origin.y − target.origin.y| ≤ 0.5·target.size`. This is the widen merge's W-F1 test.
- The target's origin and size come from the TextBlock. For a hand-built block, they come from the page span matching its bbox.
- Every other overlapping span is split by its bbox centre against the target's centre.
- Measured: this passes all 868 tests and every layout, and the target's own superscript is erased along with it.

**R3: the floor.**
- Keep 15% of the target's height. Its purpose is to guard against a degenerate or inverted band and against the one-sided 10% minimum; it is not about being "above the removal threshold".
- Below the floor, raise `RefusedBeforeMutation` before any mutation, with the fingerprint unchanged (verified).

**R4: vertical text.** A target whose direction is not near-horizontal (within 1e-3 of (1,0)) is refused, before any mutation, when its band overlaps another line's span. Today it silently deletes those spans. Clipping across the other axis is a possible later extension.

**R5: Type3.** A Type3 target keeps today's full rect, because MuPDF's glyph box for Type3 does not match the span bbox and a clipped band may not remove it. This is stated as a limitation.

**R6: N2 geometry, replacing the 15% band.**
- A layout rule clips the rect when both of these hold:
  - it extends beyond the target on both sides, or starts left of it;
  - its stroke lies entirely above the target's ink top or entirely below its ink bottom.
- The ink top and bottom come from the resolved font's glyph bboxes, or else from a cap height of 0.75·size and a descender of 0.25·size.
- A rule that crosses the ink zone is left as it is today.
- The clip also applies to rules that lie **outside the rect but within 0.5pt of its edge**.

**R7: the bleed margin (P4, re-measured).** The redaction fill bleeds 0.50pt on every side. So every N2 clip stops 0.5pt short of the rule's stroke. A 0.25pt margin still damages 128 px; 0.5pt damages 0.

**R8: the target's own rules.**
- Drawings contained in the *unclipped* rect, such as the target's own underline or strike-through, are still removed. Do this with a first pass over the full rect using `text=1, graphics=1, images=0, fill=False`.
- Without it, a tight-leading erase leaves the underline orphaned.

**R9: N3 is option (b).**
- For image-backed targets:
  - pass 1: the clipped rect with `text=0` (a `fill=False` is fine here);
  - pass 2: the full rect with `text=1, images=2, graphics=0`, plus the fill.
- Measured on a synthetic scan at pitch 13:
  - no OCR words lost (option (a) lost 15 of 18);
  - the target's ink fully blanked;
  - the result does not depend on the order of the passes.
- Known: `images=2` stores the page image uncompressed. That predates this change; document it.

**R10: scope.**
- The clip applies at the four text call sites: `delete_block`, `replace_text` on both paths, and `move_block`'s source.
- `replace_image`'s own `_clean_erase` is untouched.
- `redact_region` is unchanged.

**R11: fixtures.** No existing fixture has lines whose boxes overlap, so new ones are required:
- 3-line paragraphs at pitches 18 down to 11, covering delete, replace (widen path), replace (box path) and move;
- the first and last lines of a paragraph;
- a same-line bold label followed by body text, at tight leading;
- a target with its own superscript;
- a neighbour with a subscript;
- a synthetic scan with OCR at pitch 13 (not `sandwich.pdf`, which has no tight lines);
- the owner's form at 14pt and at 18pt;
- a bordered table;
- vertical text;
- a Type3 target.

The mutation gate adds one case for R2: revert the same-line rule, and the two replace_text same-line tests must fail.

**R12: limitations to state.**
- Neighbours whose ink is not in the text layer (outlined glyphs, drawings, scanned ink) still take sliver damage from the fill.
- Widget appearance spans are a pre-existing quirk.

### Corrections to the brief

- E1's form was wrong (see R1), and Type3 is an exception to it.
- The 15% floor's justification was wrong (see R3).
- "Same-line neighbours are left to the pad rule" was undefined (see R2).
- N2's 15% band and "just short of the stroke" both failed on the owner's form (see R6 and R7).
- `sandwich.pdf` cannot exercise N3.
- The contract "existing tests pass unedited" holds only with R2.
