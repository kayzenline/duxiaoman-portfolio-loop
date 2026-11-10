I'll review the hardening change against the brief and the locked tests, starting with the requirements and the gate code that actually changed.The task text and earlier review notes disagree on fail-closed versus offline. I'll read the gate, reviewer, and tests against the current brief.The hardening matches the updated gate rules: unreachable `origin` fails closed, the reviewed merge-base is fixed on an annotated `gate/<task>` tag, and post-pass commits are limited to the gate’s own evidence layout.

`mark` compares `merge-base(PR base, PR head)` to the `base_sha` stored on that tag. That is the start of the three-dot diff the reviewer saw, including after a parent branch is merged and the PR is retargeted. Branch-name equality would reject that retarget. Evidence after the tagged head must be status `A` or `M` and match `LOOP_LAYOUT`. `--untracked-files=all`, NUL-delimited spec diffs, unchanged-hash relock, the trailing NDJSON line, and “don’t idle out after a result” are all in place. T4’s allowed list no longer includes `e2e/*`, so it no longer covers T3’s spec files.

`★ Insight ─────────────────────────────────────`
A stacked slice is gated against its parent, so the reviewed range starts at `merge-base(parent, HEAD)`, not at `main`. After that parent lands, GitHub’s three-dot diff starts at the same commit even though the PR’s base branch name changed. Pinning that SHA on the annotated tag keeps a later evidence commit from rewriting the recorded base in `.loop/state`.
`─────────────────────────────────────────────────`

Residual risks, none of which open a false pass on their own:

- `lock_spec` force-moves `spec/<task>` before the reachability check. If `origin` is unreachable or the push fails, the local tag has already moved and the journal/state update never runs. The next gate still refuses until the remote tag matches, but the lock anchor moved on a failed command.
- Scope and the reviewer prompt diff ``base_sha..HEAD`` (live `HEAD`). The tag and the review worktree use the SHA captured at gate start. A check that creates a commit makes the prompt describe a different tree than the one tagged `gate/<task>`.
- `mark`’s `git fetch origin` has no timeout and does not set `GIT_TERMINAL_PROMPT=0`, so a credential prompt can hang it. The spec-tag lookup is bounded; this path is not.
- The scope bullet in `loop/README.md` still describes `git diff main...HEAD`. The gate now diffs the frozen merge-base SHA.

```json
{"verdict": "pass", "blocking": [], "suggestions": ["Move the spec tag only after origin is reachable and the push succeeds; a failed lock_spec currently leaves spec/<task> moved and state/journal unchanged.", "Diff the snapshotted head SHA in check_scope and review_prompt so the prompt, worktree, and gate tag cannot diverge if a check commits.", "Give mark's git fetch the same timeout and GIT_TERMINAL_PROMPT=0 bound as remote_tag.", "Update the README scope bullet to describe the frozen merge-base diff."]}
```