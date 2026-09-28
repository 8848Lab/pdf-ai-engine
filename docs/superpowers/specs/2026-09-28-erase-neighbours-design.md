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
