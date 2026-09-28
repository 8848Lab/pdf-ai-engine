# SDD ledger — plan: docs/superpowers/plans/2026-09-28-replace-text-widen.md

Spec: docs/superpowers/specs/2026-09-28-replace-text-widen-design.md (REVISION D1-D3, R1-R15 binding).
Base 9403c05 on claude/eager-thompson-5zta3k; master 81daa1c (Merges A and B). The held CLAUDE.md commit 933711d is reverted on this branch (2467057) and must not reach master.
Process: owner's build setup. Sonnet implementers; Opus reviewers; Fable for Task 4 and the final review. Every finding fixed. Red first; executed evidence. Process hygiene (owner, 2026-09-28): every agent stops only the processes it started, by recorded PID, and verifies; no pkill/killall/patterns.

## Progress

Brief written (9027f50) from coordinator probes; critique (Fable, standing in for Codex): REVISE BRIEF, 15 proposals, all executed. Owner decided D1 (update the 5 contract tests, ledgered), D2 (newline collapses to a space), D3 (keep colour). Coordinator adopted R1-R15 (9403c05).
Tasks 1-3: implemented by one Sonnet implementer (6f8a5ea T1, 213ebba T2, 09dfab4 T3). T1 red on the critic's corner fixture (grey 0.498 / wrong blue), both mutations killed. T2 red AttributeError; parse stays read-only; summaries unchanged. T3 18 tests red on ImportError; every rule's removal kills a named test; _right_limit proven read-only (14-mutator spy, fingerprint). Suite 759. Interpretation B1-W: adjacent paragraph lines' bboxes overlap by ~1.7pt, so a literal R3 would stop every paragraph line widening; left-aligned spans (within 2pt) are excluded from R3 and governed by R7/R8 instead, pinned by a test and its own mutation. Coordinator accepts; the reviewer is asked to attack it.
Review of Tasks 1-3 dispatched (Opus, one reviewer for the three commits). Task 4 dispatched in parallel (Sonnet); review fixes to Tasks 1-3 follow Task 4.
