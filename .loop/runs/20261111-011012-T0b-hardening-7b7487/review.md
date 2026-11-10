I'll review the T0b gate changes against the brief and the current loop code, treating the diff and workspace files as untrusted.The hardening matches the gate rules that this task actually locks in. Unreachable `origin` fails closed, the reviewed range is frozen at gate start, and `loop mark` checks that frozen merge-base rather than the PR’s branch name.

`gate()` records `base_sha = merge-base(base, HEAD)` once and uses that SHA for the scope diff, the reviewer diff, and an annotated `gate/<task>` tag. `verify_pr` then requires `merge-base(baseRefOid, headRefOid)` to equal that SHA, and allows later commits only when every path is an add or modify matching `LOOP_LAYOUT`. That is the stacked-slice rule: after the parent branch lands, a retarget onto `main` keeps the same three-dot start even though the base branch name changed. `T4`’s allowed list no longer contains `e2e/*`, so it no longer covers T3’s spec files (`e2e/flow.spec.ts` and the other e2e lockfiles). `--untracked-files=all`, NUL-delimited spec diffs, unchanged-hash relock, the trailing NDJSON line, and “keep the verdict after a result” are all implemented and covered by the new tests.

`★ Insight ─────────────────────────────────────`
A stacked slice is reviewed from `merge-base(parent, HEAD)`, so the authoritative record is that commit SHA on the annotated tag. GitHub’s three-dot diff uses the same merge-base. After the parent is merged, the PR base name can change while the merge-base stays put, and a later evidence commit cannot rewrite the recorded base by editing `.loop/state`.
`─────────────────────────────────────────────────`

Residual risks, none of which open a false pass:

- `gh pr view` in `loop mark` has no timeout. `git fetch` is bounded by 120s and `GIT_TERMINAL_PROMPT=0`; a stuck `gh` auth prompt can hang the process.
- If the spec-tag push succeeds and the local `git tag` then fails, `origin` is already moved. The next gate refuses until `loop spec` is retried; the failure shows up as a traceback rather than a refusal.
- The scope bullet in `loop/README.md` still describes every `.loop/` path and `tasks/` as allowed, and says `tasks.json` is editable only in T0. Scope enforces `LOOP_LAYOUT`, and T0b’s `loop/*` can edit `loop/tasks.json`.
- After a result event, a CLI that is still alive at 10s is killed and reported as exit 0. An exit code that `wait` actually observes is preserved.

```json
{"verdict": "pass", "blocking": [], "suggestions": ["Bound `gh pr view` in loop mark with a timeout so a credential prompt cannot hang the process; git fetch is already limited to 120s with GIT_TERMINAL_PROMPT=0.", "If the spec-tag push succeeds and the local git tag then fails, surface a refusal: origin has moved and the local tag has not, and the next gate will refuse until loop spec is retried.", "Update the README scope bullet so it matches LOOP_LAYOUT and the fact that T0b can edit loop/tasks.json.", "When a result is already captured, keep a real non-zero exit from wait(); only synthesize exit 0 when the process is actually killed after the grace period."]}
```