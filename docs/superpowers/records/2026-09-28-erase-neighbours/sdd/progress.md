# SDD ledger — plan: docs/superpowers/plans/2026-09-28-erase-neighbours.md

Spec: docs/superpowers/specs/2026-09-28-erase-neighbours-design.md (REVISION R1-R12 binding). Base: master f881d95 (Merges A, B and the widen merge).
Process: owner's setup; process hygiene (stop only your own processes, by PID). Sonnet implementer; FABLE review for Tasks 1-3 (data loss) and the final review.

Brief (0248a9f) from coordinator probes; critique (Fable for Codex): REVISE BRIEF, R1-R12 adopted by the coordinator. No owner decision needed: the prototype passes all 868 existing tests with R2.
Tasks 1-3: implemented (1b81593 T1, 9cee8a7 T2, d5fc2b3 T3), Sonnet. Red 67/98 new tests against an unclipped stub; every listed mutation killed (R2's by the two existing same-line replace_text tests, as planned). Suite 966, existing tests unedited. Interpretations recorded by the implementer (for the reviewer to attack): I1 glyph-bbox ink band for Base-14 only, else 0.75/0.25 fallback; I2 N2 search bounded to one rect-height beyond the clip; I3 PyMuPDF quirk: graphics=1 does not treat a drawing flush with the rect edge as contained, so R8's pass pads 0.5pt (and the same quirk exists pre-existing in the plain erase path; parked as P7); I4 R8's pass re-applies the N2 clip so it cannot remove a protected layout rule; I5 R8 only runs when a clip narrowed the rect; I6 direction None treated as horizontal; I7 N3 pass 1 uses graphics=0 images=0.
Review of Tasks 1-3 dispatched (FABLE).
