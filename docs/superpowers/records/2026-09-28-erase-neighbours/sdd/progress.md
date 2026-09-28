# SDD ledger — plan: docs/superpowers/plans/2026-09-28-erase-neighbours.md

Spec: docs/superpowers/specs/2026-09-28-erase-neighbours-design.md (REVISION R1-R12 binding). Base: master f881d95 (Merges A, B and the widen merge).
Process: owner's setup; process hygiene (stop only your own processes, by PID). Sonnet implementer; FABLE review for Tasks 1-3 (data loss) and the final review.

Brief (0248a9f) from coordinator probes; critique (Fable for Codex): REVISE BRIEF, R1-R12 adopted by the coordinator. No owner decision needed: the prototype passes all 868 existing tests with R2.
Tasks 1-3: implemented (1b81593 T1, 9cee8a7 T2, d5fc2b3 T3), Sonnet. Red 67/98 new tests against an unclipped stub; every listed mutation killed (R2's by the two existing same-line replace_text tests, as planned). Suite 966, existing tests unedited. Interpretations recorded by the implementer (for the reviewer to attack): I1 glyph-bbox ink band for Base-14 only, else 0.75/0.25 fallback; I2 N2 search bounded to one rect-height beyond the clip; I3 PyMuPDF quirk: graphics=1 does not treat a drawing flush with the rect edge as contained, so R8's pass pads 0.5pt (and the same quirk exists pre-existing in the plain erase path; parked as P7); I4 R8's pass re-applies the N2 clip so it cannot remove a protected layout rule; I5 R8 only runs when a clip narrowed the rect; I6 direction None treated as horizontal; I7 N3 pass 1 uses graphics=0 images=0.
Review of Tasks 1-3 dispatched (FABLE).
Review of Tasks 1-3 (Fable): Spec ❌, needs fixes. Holds: no neighbour lost and no target left at all four sites across leading 1.0-1.6, sizes, sub/superscripts, drop caps, columns, tables, rotations, crops, Form XObjects and libreoffice-form.pdf; refusals pre-mutation (except F1); scans lose no OCR words.
- F1 Important: R4 bypassed for hand-built blocks (dir is on the line dict, not the span): rotated neighbours deleted on the box path.
- F2 Important: _n2_ink_band passes a glyph id where glyph_bbox takes a codepoint; the band is wrong; M8/M9 survive.
- F3 Important (regression vs master at 1.2 leading): R8's 0.5pt pad removes the underline of the line above.
- F4 Important: none of the 98 tests assert on exported bytes; leftover pixels never asserted.
- F5 Important: with real embedded fonts at tight leading the fill bleed shaves neighbour descenders (Liberation 48 px, DejaVu 24 px at zoom 4).
- F6 Important: on image-backed pages the target's own drawing is left in the file (both N3 passes graphics=0); M10 survives.
- F7 Minor: the 0.5pt margin sits on the bleed edge (one border pixel row at zoom 4); F8 docstring (stroke half-width, not a quirk; P7 narrowed); F9 dead proximity bound and over-broad "starts left"; F10 limitation (a rule crossing descenders at pitch 12 still notches, as R6 allows); F11 images=2 stores images raw (25.6x on a scan; tobytes(deflate=True) would fix it at export, pre-existing, for the owner).
Fix round 1 dispatched to the original implementer (F1-F9).
