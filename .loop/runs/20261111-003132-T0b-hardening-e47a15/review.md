I'll review the T0b-hardening change against the brief and the locked gate tests, starting with the requirements and the code that actually implements them.The earlier gate review describes the merge-order and offline-tag behavior this change was supposed to adopt. I'll read that suggestion and check the new code against it.The gate still fails offline when `origin` is configured, so this change does not meet the offline-tolerant tag lookup requirement. The other T0b items behave as specified.

`check_spec` turns a failed `git ls-remote` into a hard failure:

```141:143:loop/gate.py
    remote = remote_tag(root, tag)
    if remote is UNREACHABLE:
        return [f'Cannot verify {tag} against origin (offline?); refusing to pass']
```

`remote_tag` returns `UNREACHABLE` on both a 20s timeout and any non-zero `ls-remote` status. A clone that has `origin` set therefore still cannot pass the gate without a network. That is the failure round-4 described: a dead `ls-remote` used to look like a missing tag (`''`) and was reported as "local tag differs from origin"; the new path reports it honestly and still refuses the pass. Offline tolerance means the gate continues on the local `spec/<task>` tag when the query cannot reach origin. A query that succeeds and shows the tag missing or pointing at a different commit should still fail closed. Nothing in `loop/tests/test_gate.py` installs an origin and fails `ls-remote`, so the suite stays green either way.

The rest of the task holds.

- `--untracked-files=all` is on both porcelain calls, so an untracked `.loop/runs/<id>/` is judged file-by-file against `LOOP_LAYOUT`. `test_uncommitted_gate_evidence_does_not_break_scope` covers that.
- An unchanged spec hash leaves `failures` in place; a real hash change clears them. Both are tested.
- A final NDJSON line with no newline is parsed, and once a `result` event is in, the idle timer stops. A process that then stays quiet is killed after 10s and the captured text is returned with status 0, so `review()` keeps the verdict. A non-zero exit inside that 10s still fails the review.
- `check_spec` splits `git diff --name-only -z` on NUL.
- T4's `allowed` list no longer contains `e2e/*`, so it no longer covers T3's spec (`e2e/flow.spec.ts` and the other e2e spec files).

The merge-order check is the right one for the peer-session finding. `gate` stores `merge-base(base, HEAD)` as `base_sha`. `verify_pr` requires `merge-base(baseRefOid, headRefOid)` to be that same commit, and allows later commits only when every path matches `LOOP_LAYOUT` with status `A` or `M`. That is the start of the three-dot diff the reviewer saw. The new test covers a PR aimed at `main` while the gate base was `mid`, the same PR after `mid` is merged with `--no-ff`, and a post-pass `src/` commit.

`★ Insight ─────────────────────────────────────`
`git diff base...HEAD` starts at `merge-base(base, HEAD)`, which stays put when `main` merely gains a merge commit of the old base. Comparing the base branch's current tip to `baseRefOid` rejects that retarget even though the PR file list is the one that was reviewed.
`UNREACHABLE` is a sentinel object, so `remote_tag(...) is not None` is true for it. `lock_spec` uses that condition to decide whether to `git push`, which couples "origin is configured" to "the lookup returned a SHA."
`─────────────────────────────────────────────────`

```json
{"verdict": "fail", "blocking": [{"file": "loop/gate.py", "line": 143, "issue": "Offline-tolerant remote tag lookup is not implemented. remote_tag maps timeout and any non-zero ls-remote to UNREACHABLE, and check_spec refuses to pass. A repo with origin configured still cannot gate offline; the old bug was a failed ls-remote reported as a spec mismatch, and this still fails the gate. Skip the origin comparison when the query cannot reach origin, and keep failing closed when the query succeeds and the tag is missing or different. No test simulates a failed ls-remote, so the suite does not catch this."}], "suggestions": ["lock_spec treats any non-None remote_tag result as a signal to force-push. UNREACHABLE takes that branch, and the push has no timeout and does not set GIT_TERMINAL_PROMPT=0.", "test_result_then_silence_keeps_verdict should assert exit code 0. review() discards the verdict on any non-zero status, and the test only checks the text.", "Add a verify_pr case for a post-pass path under .loop/ that fails LOOP_LAYOUT. The current test covers a valid result.json and a src/ file.", "base_sha is taken from .loop/state/<task>.json, and evidence commits may modify that file. Record the reviewed merge-base on the gate/<task> tag and read it from there.", "loop/README.md still describes mark as head equality plus any .loop/ evidence commit."]}
```