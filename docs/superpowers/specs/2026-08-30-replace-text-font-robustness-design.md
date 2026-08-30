# 8848 PDF — replace_text Font Robustness — Design

## Overview

`replace_text` (v0.2) currently requires `target.font` to be one of
PyMuPDF's built-in Base-14 fonts (Helvetica, Times, Courier, Symbol,
ZapfDingbats and their bold/italic variants), since it can only draw
replacement text with a font it can load. A reliability spike run against
two genuinely real-world PDFs (a real IRS Form 1040, a real arXiv paper)
found this fails on effectively 100% of real content: both documents use
exclusively embedded, non-Base-14 fonts (`HelveticaNeueLTStd-Roman`,
`NimbusRomNo9L-Regu`, `ArialMT`, `CMMI10`, ...) — 100% and 99% of their
text blocks respectively. `redact_region`, by contrast, is font-agnostic
and passed the same spike with zero failures across 60 sampled blocks plus
two exhaustive whole-page batch redactions — it needs no changes here.

This spec makes `replace_text` draw with the block's own real font instead
of only ever falling back to a generic built-in — closing the actual gap
the spike found, rather than adding an unrelated new capability.

## Non-goals (explicit, this pass)

- No change to `redact_region` — already verified robust, out of scope.
- No change to the shrink-retry loop's sizing logic, the background-color
  sampling, or `_insertion_rect`'s geometry math — those are unaffected by
  which font gets used and stay exactly as they are.
- No attempt at 100% Unicode coverage in an absolute sense — no font
  covers literally every codepoint ever assigned. The three-tier design
  below is verified against Latin, Cyrillic, Greek, CJK, and common
  symbols/currency/punctuation with zero gaps found in this project's own
  testing; it is not a formal guarantee for every conceivable script.
- No new package dependency and no bundled font asset — the final fallback
  tier uses a font PyMuPDF already ships internally (see below), not
  something this repo needs to vendor or maintain.
- No caching of extracted/embedded fonts across separate `replace_text`
  calls — each call re-resolves independently. `webui/session.py` already
  re-parses the whole document (a fresh `fitz.Document` handle) after
  every mutation, so there is no live handle that persists across calls in
  this product's actual usage pattern for repeated embedding to optimize
  away. Note this does NOT mean file growth is a non-issue: PyMuPDF's own
  `insert_font` deduplicates identical buffers, but only within one live
  `fitz.Document` handle (verified: 5 repeated inserts of the same 3.4MB
  fallback font buffer, all on the same handle, produced one 3.4MB export,
  not five). It does NOT deduplicate across separate parse/export cycles on
  freshly-reopened handles — exactly the pattern `webui/session.py` uses.
  Verified: three separate `replace_text` calls each needing the Tier 3
  fallback, each on a freshly re-parsed handle (mimicking the real webui's
  actual call pattern), produced three separate ~3.5MB embeds, not one
  shared copy (measured: exported sizes grew roughly 3.57MB → 7.14MB →
  10.71MB across the three re-parse cycles, not staying flat). Tier 3 is a
  rare last-resort path, and fixing this file-growth tradeoff is out of
  scope for this pass — this note exists only so the tradeoff is
  accurately documented, not silently assumed away by the (true-but-
  narrower) same-handle dedupe behavior above.

## Architecture

**Three-tier font resolution**, tried in order for every `replace_text`
call, replacing today's single flat "must already be Base-14" check:

**Tier 1 — the block's own real font.** `target.font` (e.g.
`"HelveticaNeueLTStd-Roman"`) is matched against the page's actual font
resources via `page.get_fonts(full=True)`, stripping the 6-uppercase-letter
subset-tag prefix real PDFs commonly add to an embedded font's PostScript
name (e.g. `"PIMSLO+HelveticaNeueLTStd-Roman"` — confirmed on the real IRS
form; the tag format is fixed at exactly 6 letters + `+` per the PDF
spec). The matching resource's bytes are extracted via
`doc.extract_font(xref)` and re-embedded on the page via
`page.insert_font(fontname=..., fontbuffer=...)`. Verified end-to-end
against both real documents in this spec's spike: extraction, embedding,
and drawing all succeeded, and the exported PDF opened cleanly.

**Tier 2 — Base-14 fallback**, reached only if Tier 1's font can't be
resolved (extraction fails, the resource isn't found, or the buffer isn't
a usable font) or doesn't cover every character the replacement text
needs. Uses `target.font` directly if it already is a Base-14 name
(today's only success path, unchanged for that case); otherwise a small
bold/italic heuristic on `target.font`'s own name (case-insensitive
`"bold"` / `"italic"` or `"oblique"` substrings) picks a reasonably
matching generic Helvetica variant rather than silently dropping styling
information.

**Tier 3 — PyMuPDF's bundled broad-coverage font**, the true last resort,
reached only if neither tier above covers every character needed.
PyMuPDF ships an internal font reachable via the reserved name `"cjk"`
(also aliased as `"china-s"`, `"japan"`, `"korea"`, etc. — all verified to
resolve to the identical resource) — despite the name, it is not
CJK-only: tested in this spec's spike against Latin A-Z/a-z/0-9, common
punctuation, Cyrillic, Greek, CJK ideographs, currency symbols, and
typographic dashes/quotes, with **zero missing glyphs** in every category.
Confirmed it actually draws correctly too (not just `has_glyph`-true): a
test string mixing `@#%`, Chinese, Greek Ω, and `$100` rendered correctly
in one line. Accessed via `fitz.Font("cjk").buffer`, re-embedded the same
way as Tier 1. One regular weight only — no bold/italic variant exists at
this tier, which is an accepted tradeoff: by the time this tier is
reached, rendering *something* correct takes priority over matching the
original's exact styling.

**Glyph coverage check.** Before committing to a tier, every character in
`new_text` is checked against that tier's actual font via
`fitz.Font.has_glyph(ord(char))` — **except the space character**, which
real PDF fonts routinely omit as an actual glyph (word spacing is handled
by positioning, not a drawn glyph) even though `insert_textbox` renders it
correctly regardless; checking it produces false "missing" reports.  This
check is what catches the failure mode the spike found: PyMuPDF's
`insert_textbox` does **not** raise or warn when asked to draw a character
missing from a font's (typically subsetted) glyph set — it silently omits
that character from the output. Verified visually: replacement text with
`@#%` in it rendered with those characters (and one space) simply absent,
no error, no visible gap marker. Every tier is glyph-checked before use,
so this silent-drop behavior can never reach a real document through this
engine.

**Final failure.** If no tier covers every character, `replace_text`
raises `ValueError` naming the specific unrenderable character(s) — a
meaningfully rarer and more actionable failure than today's flat
"not Base-14", since by this point the block's real font, a styled
Base-14 substitute, AND a font verified to cover Latin/Cyrillic/Greek/CJK/
common symbols have all been tried and failed. This preserves the
existing function's core guarantee (checked in full before any page
mutation — the erase step still happens exactly once, after font
resolution succeeds, never before).

## Data flow inside `replace_text`

1. `new_text` non-empty, `page_index`/`target.bbox` valid, `target.size`
   positive — unchanged from today.
2. **New:** resolve the font via the three-tier process above, using
   `new_text` to drive the glyph-coverage decision. Raises `ValueError`
   here (before any mutation) if all three tiers fail.
3. `_insertion_rect` (unchanged internal logic) now takes the *resolved*
   `fitz.Font` object directly for its ascender/descender metrics, instead
   of always building one from `_base14_font(target.font)`.
4. Erase once, run the existing shrink-retry loop — both unchanged in
   structure, just drawing with the resolved font's alias instead of
   `target.font` directly.

## Testing strategy

Extends the existing `engine/` test suite (deterministic, no network) with:

- A fixture PDF containing a block with a genuinely embedded, non-Base-14,
  subsetted font (generated the same way `tests/fixtures/generate_fixtures.py`
  builds other fixtures, using PyMuPDF's own font-embedding on write) — the
  new success path this whole spec exists for.
- A case where Tier 1 fails (font not embedded/extractable on the fixture)
  but Tier 2 succeeds (e.g. `target.font` already Base-14, or a
  bold-named font falling back to `helvetica-bold`).
- A case where new_text needs a character outside the embedded fixture
  font's subset — proves the fallback cascades to Tier 2/3 rather than
  drawing an incomplete result.
- A case where new_text needs a character (e.g. a CJK character or `Ω`)
  that only Tier 3 covers — proves the cascade reaches the bundled font
  and draws it correctly.
- A case where no tier can cover a needed character (an invented,
  never-assigned codepoint) — proves the final `ValueError` names the
  actual missing character(s) and that nothing was modified.
- A regression check that today's existing Base-14 fixture tests still
  pass unchanged (Tier 2's "already Base-14" path is exactly today's
  behavior for that case).
- Real-document confirmation (manual, not part of the automated suite —
  same "no network calls in the automated suite" rule this project has
  followed throughout): re-run this spec's own spike against the IRS form
  and arXiv paper PDFs used to find the original gap, confirming
  `replace_text` now succeeds on real blocks from both.

## Explicitly out of scope (this pass)

- Bold/italic *detection and matching* for Tier 1's real embedded font
  (not needed — Tier 1 uses the block's actual font file, which already
  carries its own real weight/style; the heuristic is only relevant to
  Tier 2's generic substitute).
- A user-facing setting to prefer one tier over another, or to disable a
  tier — the cascade is always tried in the same fixed order.
- Any change to how blocks are *found* or *identified* (parser.py,
  webui/session.py's block registry) — this is purely an
  `engine/operations.py` change.
