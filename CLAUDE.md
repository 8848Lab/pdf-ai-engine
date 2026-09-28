# Working rules for agents in this repository

## Background processes: clean up your own, and only your own

Every agent — the coordinating session and every subagent it starts — must
close every process it started before it reports back, and must never touch a
process it did not start. Other sessions and agents may be running servers,
browsers or test runs in the same container at the same time.

- **Record the PID of everything you start in the background**, at the moment
  you start it: `cmd > "$LOG" 2>&1 & echo $! > "$PIDFILE"`. Use a PID file in
  your own scratchpad directory.
- **Stop it by that PID**, not by name or pattern: `kill "$(cat "$PIDFILE")"`.
  Never use `pkill -f`, `killall`, or a pattern match such as
  `pkill -f uvicorn`. A pattern can match another agent's process.
- **Verify it is gone** before reporting: `kill -0 "$(cat "$PIDFILE")"` must
  fail, and any port you bound (e.g. `curl -s localhost:<port>`) must no
  longer answer. Say in your report that you checked.
- **Use a port nobody else is using** for servers you start, and name it in
  your report, so a later cleanup can be checked against it.
- **Worktrees you create are yours to remove** (`git worktree remove`), and
  only those. Leave any worktree you did not create alone, and mention it.
- **Playwright/Chromium**: close the browser in a `finally` (`await
  browser.close()`), so a failed run does not leave it running.
- If you find a process or worktree you believe is stale but did not start,
  **report it; do not stop it.** The coordinator decides.

This applies on top of the owner's build process recorded in the ledgers under
`docs/superpowers/records/`.
