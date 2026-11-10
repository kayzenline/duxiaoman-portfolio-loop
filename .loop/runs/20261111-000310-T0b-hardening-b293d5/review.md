I'll review the T0b-hardening change against the brief and the gate tests, starting with the requirements and the code that actually changed.The merge-order check in `mark` can accept a pull request whose GitHub diff is not the diff the gate reviewed. The other T0b items (untracked files, spec relock, stream parsing, offline tag lookup, `check_spec -z`, and dropping `e2e/*` from T4) match the task.

`mark` stores the `--base` argument as a branch name (`entry['base']` in `loop/gate.py`) and then allows a PR targeting `main` when that name’s current tip is an ancestor of local `main`:

```58:62:loop/__main__.py
        base = e.get('base', 'main')
        merged_base = base != 'main' and subprocess.run(
            ['git', 'merge-base', '--is-ancestor', base, 'main'], cwd=root, capture_output=True).returncode == 0
        if pr['baseRefName'] != base and not (pr['baseRefName'] == 'main' and merged_base):
            sys.exit(f"Refusing: PR base {pr['baseRefName']} != gate base {base} (and {base} is not merged into main)")
```

The gate diff is `base...HEAD` against whatever commit that name resolved to at gate time. Local `main` is not the PR’s base commit. Merging `feat` into local `main` without updating GitHub `main` makes `merged_base` true, so the same gated head opened against GitHub `main` is accepted even though that PR still contains the commits the gate treated as base. The reverse fails too: after GitHub merges and deletes `feat`, `is-ancestor` cannot resolve the name, and a PR that was correctly retargeted to `main` is refused.

`★ Insight ─────────────────────────────────────`
`git diff A...B` is “changes since the merge-base with the commit `A` resolved to then.” A branch name is not that commit, and local `main` is not `baseRefOid`. The check has to snapshot `git rev-parse <base>` at gate time and test that SHA against the PR’s base commit.
`stream` returns exit code 0 after a captured result whenever the child is still alive, including when `p.wait()` already exited non-zero. `review()` only treats a non-zero code as an infrastructure failure, so that path can turn a crashed reviewer into a normal verdict. Returning 0 is required only after the linger kill; a finished non-zero exit should still surface.
`─────────────────────────────────────────────────`

What holds: `--untracked-files=all` is on both status calls, so files inside an untracked `.loop/runs/` directory are judged with `LOOP_LAYOUT` (the new evidence test covers that). Unchanged spec hashes keep `failures`. A final NDJSON line with no newline is parsed, and a result ends the idle loop. `remote_tag` maps timeout and any `ls-remote` failure to “skip,” and a missing tag online still returns `''` so `check_spec` fails closed. `check_spec` splits on NUL. T4’s `allowed` list no longer includes `e2e/*`, so it no longer covers T3’s spec files.

```json
{"verdict": "fail", "blocking": [{"file": "loop/__main__.py", "line": 59, "issue": "Merge-order allowance checks whether the live branch name stored at gate time (loop/gate.py entry['base']) is an ancestor of local main. Local main can contain that branch while the GitHub PR base does not, so mark accepts the same gated head when the PR diff still includes commits the gate excluded as base. If the base branch was deleted or moved after merge, the same check either refuses a PR GitHub retargeted to main or accepts one whose base commit is no longer the commit that was diffed."}], "suggestions": ["Snapshot git rev-parse of the gate base and compare that SHA to the PR baseRefOid; fail closed when the object is not available locally.", "In stream(), return 0 only after the linger SIGKILL. If p.wait() completes, return that status so review() still rejects a non-zero reviewer exit.", "remote_tag treats every ls-remote failure as offline and can block 20s before skipping the tamper check. Limit that to timeout or network errors and set GIT_TERMINAL_PROMPT=0.", "There is no test for mark (wrong base, base already merged, evidence outside LOOP_LAYOUT). test_unexpected_loop_paths_are_rejected only matches the regex, and test_relock does not show that a real spec change still clears failures.", "check_clean still exempts every path under .loop/, and gitignored files can still change check results."]}
```