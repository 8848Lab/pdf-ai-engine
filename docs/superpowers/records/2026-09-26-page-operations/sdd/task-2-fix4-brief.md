# Task 2 — fix round 4 brief (two coordinator findings on round 3)

Context: `engine/geometry.py`'s `drawing_refusal` decides when the editor must refuse to draw on a PDF page. It reads MuPDF's own page transform (ruling C16). Round 3 (a8b2406) implemented it. The implementer reported two open points; the coordinator verified both and rules as follows.

**F1: the sub-point (`width < 1 or height < 1`) check has no test that fails without it.** Round 3's mutation 2 broke nothing, because the size-tolerance check happened to catch the existing tiny-box rows too.
- The coordinator found a row that needs the check: `/MediaBox [0 0 612 792] /CropBox [100 100 100.995 100.995]`.
- MuPDF swaps the 0.995pt box for the unit rect, so `page.rect` is (0, 0, 1, 1). That is within the 0.01pt tolerance of 0.995, but the origin moves, and text drifts to (200, 40.005).
- With the `< 1` check removed (executed on a scratch copy), the gate returns None: a bypass.

Add this row to the Test B table as `crop-0.995`, category `incons`, next to the other `crop-tiny` rows. Then re-run mutation 2 and confirm `crop-0.995` fails without the check.

**F2: the "(1)" message.** `{unit:.7g}` still prints "1" for a measured scale of 1.0000001192092896. Change it to `{unit:.10g}`, which prints "1.000000119". Then update the regression-canary assertion round 3 added for `unit-1.0000001-huge`, so it asserts the message does NOT contain "scaling (1)".

Touch only `engine/geometry.py` (the one format spec) and `tests/test_geometry.py`. Run the red-first check for F1's new row: it must fail with the `< 1` check removed, and pass with it restored. Then run the full `tests/` suite. Save the full output and the exit status.

Append a "Fix round 4" section to `task-2-report.md`, and commit on top of HEAD (no amend, reset or rebase) with:

    fix: pin the sub-point crop check with a row that needs it, and print the full /UserUnit scale

    Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
    Claude-Session: https://claude.ai/code/session_016ns89haVgmSD9aXKkdw3Ka
