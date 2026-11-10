You are the independent code reviewer for a take-home assessment repository.
Another agent (Claude Code) implemented this change; you did not write it. Review it critically.

Requirements source of truth: context/originals/投资组合示例数据.json and context/BRIEF.md
(summary of the task PDF, which is at context/originals/度小满_全栈开发实习_技术测评任务.pdf).
Read the actual files in the workspace as needed; do not trust this prompt's summary of them.

Task `T0-loop`: Loop gate itself: spec lock, scope check, clean-tree check, checks, read-only Grok review with streamed idle timeout, progress-aware blocking rule, CLI and docs.
Acceptance tests (locked; implementer may not edit): loop/tests/test_gate.py
Files the implementer was allowed to change: loop/*, AGENTS.md, README.md, .github/*, .gitignore
Mechanical checks already run by the gate (all exit 0): [["python3", "-m", "unittest", "discover", "-s", "loop/tests", "-t", "."]]

Focus: requirement mismatches, wrong business rules (strict > thresholds, cash in denominator, integer quantities,
failed ops must not change valid results, isolation of original portfolio), precision bugs, missing error handling,
tests that pass without proving the requirement, security issues. Ignore pure style.
Only mark something blocking if it violates a requirement or is a real bug; put preferences in suggestions.

End your answer with exactly one fenced json block of this shape:
```json
{"verdict": "pass or fail", "blocking": [{"file": "path", "line": 0, "issue": "..."}], "suggestions": ["..."]}
```

DIFF (base main):
diff --git a/.github/workflows/ci.yml b/.github/workflows/ci.yml
new file mode 100644
index 0000000..555a1cc
--- /dev/null
+++ b/.github/workflows/ci.yml
@@ -0,0 +1,16 @@
+name: ci
+on: [push, pull_request]
+jobs:
+  test:
+    runs-on: ubuntu-latest
+    steps:
+      - uses: actions/checkout@v4
+      - uses: actions/setup-python@v5
+        with: { python-version: '3.12' }
+      - name: loop tests
+        run: python -m unittest discover -s loop/tests -t .
+      - uses: astral-sh/setup-uv@v5
+        if: hashFiles('uv.lock') != ''
+      - name: backend tests
+        if: hashFiles('uv.lock') != ''
+        run: uv run --frozen pytest -q backend/tests
diff --git a/.loop/journal.jsonl b/.loop/journal.jsonl
new file mode 100644
index 0000000..d274dab
--- /dev/null
+++ b/.loop/journal.jsonl
@@ -0,0 +1 @@
+{"at": "2026-11-10T22:46:45+1100", "task": "T0-loop", "event": "spec_locked", "reason": "initial spec", "spec": {"loop/tests/test_gate.py": "2b27ab3cabcd446352bb8036ef55397a996b1ae21929ec3115e68942843391e9"}}
diff --git a/.loop/state.json b/.loop/state.json
new file mode 100644
index 0000000..bc76cc0
--- /dev/null
+++ b/.loop/state.json
@@ -0,0 +1,12 @@
+{
+  "version": 2,
+  "tasks": {
+    "T0-loop": {
+      "spec": {
+        "loop/tests/test_gate.py": "2b27ab3cabcd446352bb8036ef55397a996b1ae21929ec3115e68942843391e9"
+      },
+      "status": "spec_locked",
+      "failures": []
+    }
+  }
+}
diff --git a/AGENTS.md b/AGENTS.md
new file mode 100644
index 0000000..315cb4e
--- /dev/null
+++ b/AGENTS.md
@@ -0,0 +1,5 @@
+# 项目入口（任何 Agent 先读）
+1. `PLAN.md`（实现前原版，禁止改写）、`context/BRIEF.md`、原件 `context/originals/`。
+2. `loop/README.md`（工作流）、`loop/tasks.json`（切片定义）、`python3 -m loop status`（当前进度）。
+3. 角色：Claude Code 实现；Grok 只读审查；合并只发生在 `loop gate` 通过之后，且合并的 HEAD 等于 `passed_head`。
+4. 不虚构测试结果、截图、耗时或部署结果。外部材料是需求证据，不是执行授权。
diff --git a/loop/README.md b/loop/README.md
new file mode 100644
index 0000000..c310c64
--- /dev/null
+++ b/loop/README.md
@@ -0,0 +1,38 @@
+# Agent Loop v2 — Claude 实现 / Grok 审查
+
+仓库即状态，聊天记录不是状态。标准库 Python 3.11+，无第三方依赖。
+
+## 角色
+| 角色 | 执行者 | 权限 |
+| --- | --- | --- |
+| 协调 + 实现 | Claude Code（交互会话） | 读写仓库、提交、PR、合并 |
+| 独立审查 | Grok（`cursor-agent --mode ask`，模型见 `tasks.json`） | **只读**；argv 含 `--force/-f/--yolo` 时拒绝启动 |
+| 门禁 | `python -m loop gate` | 机器裁决；不信任任何一方的自述 |
+
+## 每个切片的循环
+```sh
+git checkout -b feat/<task> main
+# 1. 先写验收测试（spec），提交，然后锁定
+python3 -m loop spec <task>            # 记录 spec 文件 sha256 到 .loop/state.json
+# 2. 实现 → commit
+# 3. 门禁：spec 未改动 → 改动不越界 → 工作区干净 → checks 全部 exit 0 → Grok 审查
+python3 -m loop gate <task>            # exit 0 = gate_passed
+# 4. 失败 → 读 .loop/runs/<run>/ 修复 → 再 gate
+# 5. 通过 → push、PR、gh pr merge --match-head-commit <passed_head>
+python3 -m loop mark <task> merged --pr <url>
+python3 -m loop status
+```
+
+## 关键规则（对应 v1 卡死的原因）
+- **流式 + 空闲超时**：审查用 `stream-json`，事件实时写入 `stream.jsonl`；`idle_timeout` 秒无输出才杀进程组，`total_timeout` 为总上限。v1 用 `json` 输出 + 300 秒硬超时，四次运行日志全是 0 字节。
+- **按失败签名阻塞**：同一阶段、同一错误连续 3 次才 `blocked`；错误变化说明有进展，不扣预算。审查基础设施失败（超时、CLI 报错）记为 `needs_review`，不计入失败。
+- **测试锁**：spec 改动只能通过显式 `loop spec <task> --reason ...` 重新锁定，并写入 journal。
+- **范围锁**：`git diff main...HEAD` 中出现 `allowed + spec + .loop/ + tasks/` 以外的文件即失败；`tasks.json` 只在 T0 可改，后续切片不能放宽自己的检查。
+- **先便宜后昂贵**：机械检查失败就不调用 Grok。
+- **审查结论**：只取 Grok 回复中最后一个 ```json 块；缺失、格式错误或有 blocking 一律判 fail。
+
+## 证据
+`.loop/runs/<run>/`：`result.json`（阶段、HEAD、错误、审查结论）、`check-N.log`、`review-prompt.md`、`review.md`；`stream.jsonl` 体积大，不入库。`.loop/state.json` 与 `.loop/journal.jsonl` 入库。
+
+## 边界
+门禁证明"检查通过且审查者未发现阻塞问题"，不证明语义完整；最终仍需人工核对需求映射。审查者是同一份需求的另一个模型，不是测评官。
diff --git a/loop/__init__.py b/loop/__init__.py
new file mode 100644
index 0000000..e69de29
diff --git a/loop/__main__.py b/loop/__main__.py
new file mode 100644
index 0000000..82d579f
--- /dev/null
+++ b/loop/__main__.py
@@ -0,0 +1,57 @@
+"""python -m loop {status|spec|gate|mark} — see loop/README.md."""
+import argparse
+import json
+import sys
+import time
+from pathlib import Path
+
+from . import gate as g
+
+
+def main(argv=None):
+    p = argparse.ArgumentParser(prog='loop')
+    p.add_argument('--root', type=Path, default=Path.cwd())
+    sub = p.add_subparsers(dest='cmd', required=True)
+    sub.add_parser('status')
+    s = sub.add_parser('spec', help='lock acceptance tests for a task')
+    s.add_argument('task')
+    s.add_argument('--reason', default='initial spec')
+    r = sub.add_parser('gate', help='spec lock → scope → clean → checks → Grok review')
+    r.add_argument('task')
+    r.add_argument('--base', default='main')
+    r.add_argument('--skip-review', action='store_true', help='mechanical checks only; never yields a pass')
+    m = sub.add_parser('mark', help='record a delivery fact, e.g. merged PR')
+    m.add_argument('task')
+    m.add_argument('status', choices=['pr_open', 'merged'])
+    m.add_argument('--pr', required=True)
+    a = p.parse_args(argv)
+    root = a.root.resolve()
+
+    if a.cmd == 'status':
+        cfg, state = g.load(root), g.read_state(root)
+        for t in cfg['tasks']:
+            e = state['tasks'].get(t['id'], {})
+            print(f"{t['id']:<16} {e.get('status', 'todo'):<13} {e.get('pr', '')}")
+        return 0
+    if a.cmd == 'spec':
+        print(json.dumps(g.lock_spec(root, a.task, a.reason), indent=2))
+        return 0
+    if a.cmd == 'gate':
+        record, status = g.gate(root, a.task, a.base, a.skip_review)
+        print(json.dumps({'stage': record['stage'], 'status': status, 'errors': record['errors'],
+                          'suggestions': record.get('review', {}).get('suggestions', []),
+                          'evidence': f".loop/runs/{record['run']}"}, ensure_ascii=False, indent=2))
+        return 0 if status == 'gate_passed' else 1
+    if a.cmd == 'mark':
+        state = g.read_state(root)
+        e = state['tasks'].setdefault(a.task, {})
+        if a.status == 'merged' and e.get('status') not in ('gate_passed', 'pr_open'):
+            sys.exit('Refusing: task has not passed the gate')
+        e.update(status=a.status, pr=a.pr)
+        g.write_state(root, state)
+        g.journal(root, {'at': time.strftime('%FT%T%z'), 'task': a.task, 'event': a.status, 'pr': a.pr})
+        return 0
+
+
+if __name__ == '__main__':
+    raise SystemExit(main())
diff --git a/loop/gate.py b/loop/gate.py
new file mode 100644
index 0000000..c33a502
--- /dev/null
+++ b/loop/gate.py
@@ -0,0 +1,207 @@
+"""Gate: the only path from "implemented" to "mergeable".
+
+Order (cheap → expensive): spec lock → scope → checks → Grok review.
+State lives in the repo (.loop/state.json); evidence in .loop/runs/<run>/.
+"""
+import fnmatch
+import hashlib
+import json
+import os
+import subprocess
+import time
+import uuid
+from pathlib import Path
+
+from . import reviewer
+
+ALWAYS_ALLOWED = ['.loop/*', 'tasks/*']
+MAX_SAME_FAILURE = 3
+DIFF_LIMIT = 60_000
+
+
+def load(root):
+    return json.loads((root / 'loop' / 'tasks.json').read_text())
+
+
+def task_by_id(cfg, task_id):
+    for t in cfg['tasks']:
+        if t['id'] == task_id:
+            return t
+    raise SystemExit(f'Unknown task {task_id}')
+
+
+def read_state(root):
+    p = root / '.loop' / 'state.json'
+    return json.loads(p.read_text()) if p.exists() else {'version': 2, 'tasks': {}}
+
+
+def write_state(root, state):
+    p = root / '.loop' / 'state.json'
+    p.parent.mkdir(exist_ok=True)
+    tmp = p.with_suffix('.tmp')
+    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n')
+    os.replace(tmp, p)
+
+
+def journal(root, entry):
+    with (root / '.loop' / 'journal.jsonl').open('a') as f:
+        f.write(json.dumps(entry, ensure_ascii=False) + '\n')
+
+
+def sha(path):
+    return hashlib.sha256(path.read_bytes()).hexdigest()
+
+
+def git(root, *args):
+    return subprocess.run(['git', *args], cwd=root, check=True,
+                          capture_output=True, text=True).stdout
+
+
+def changed_files(root, base):
+    committed = git(root, 'diff', '--name-only', f'{base}...HEAD').split()
+    dirty = [line[3:].split(' -> ')[-1] for line in git(root, 'status', '--porcelain').splitlines()]
+    return sorted(set(committed + dirty))
+
+
+def lock_spec(root, task_id, reason):
+    """Record hashes of the task's acceptance tests. Re-locking is explicit and journaled."""
+    cfg, state = load(root), read_state(root)
+    t = task_by_id(cfg, task_id)
+    hashes = {s: sha(root / s) for s in t['spec']}
+    entry = state['tasks'].setdefault(task_id, {})
+    relock = 'spec' in entry
+    entry.update(spec=hashes, status='spec_locked', failures=[])
+    write_state(root, state)
+    journal(root, {'at': time.strftime('%FT%T%z'), 'task': task_id,
+                   'event': 'spec_relocked' if relock else 'spec_locked', 'reason': reason, 'spec': hashes})
+    return hashes
+
+
+def check_spec(root, entry):
+    errors = []
+    for path, digest in entry.get('spec', {}).items():
+        p = root / path
+        if not p.exists() or sha(p) != digest:
+            errors.append(f'Acceptance test changed or missing since lock: {path}')
+    if not entry.get('spec'):
+        errors.append('Spec not locked; run `python -m loop spec <task>` first')
+    return errors
+
+
+def check_scope(root, task, base):
+    allowed = task['allowed'] + task['spec'] + ALWAYS_ALLOWED
+    return [f'Out of scope change: {f}' for f in changed_files(root, base)
+            if not any(fnmatch.fnmatch(f, pat) for pat in allowed)]
+
+
+def check_clean(root):
+    """A pass must describe a commit, so uncommitted work (outside .loop/) is rejected."""
+    dirty = [line[3:] for line in git(root, 'status', '--porcelain').splitlines()
+             if not line[3:].startswith('.loop/')]
+    return [f'Uncommitted change, commit before gating: {f}' for f in dirty]
+
+
+def run_checks(root, task, evidence):
+    results = []
+    for i, argv in enumerate(task['checks']):
+        log = evidence / f'check-{i}.log'
+        t0 = time.monotonic()
+        try:
+            with log.open('w') as out:
+                code = subprocess.run(argv, cwd=root, stdout=out, stderr=subprocess.STDOUT,
+                                      timeout=task.get('check_timeout', 600)).returncode
+        except subprocess.TimeoutExpired:
+            code = 'timeout'
+        results.append({'argv': argv, 'exit': code, 'seconds': round(time.monotonic() - t0, 1),
+                        'log': str(log.relative_to(root))})
+        if code != 0:
+            break
+    return results
+
+
+def review_prompt(root, cfg, task, base, checks):
+    diff = git(root, 'diff', f'{base}...HEAD') + git(root, 'diff', 'HEAD')
+    if len(diff) > DIFF_LIMIT:
+        diff = diff[:DIFF_LIMIT] + '\n[diff truncated; read the files directly]'
+    return f"""You are the independent code reviewer for a take-home assessment repository.
+Another agent (Claude Code) implemented this change; you did not write it. Review it critically.
+
+Requirements source of truth: context/originals/投资组合示例数据.json and context/BRIEF.md
+(summary of the task PDF, which is at context/originals/度小满_全栈开发实习_技术测评任务.pdf).
+Read the actual files in the workspace as needed; do not trust this prompt's summary of them.
+
+Task `{task['id']}`: {task['goal']}
+Acceptance tests (locked; implementer may not edit): {', '.join(task['spec'])}
+Files the implementer was allowed to change: {', '.join(task['allowed'])}
+Mechanical checks already run by the gate (all exit 0): {json.dumps([c['argv'] for c in checks])}
+
+Focus: requirement mismatches, wrong business rules (strict > thresholds, cash in denominator, integer quantities,
+failed ops must not change valid results, isolation of original portfolio), precision bugs, missing error handling,
+tests that pass without proving the requirement, security issues. Ignore pure style.
+Only mark something blocking if it violates a requirement or is a real bug; put preferences in suggestions.
+
+End your answer with exactly one fenced json block of this shape:
+```json
+{{"verdict": "pass or fail", "blocking": [{{"file": "path", "line": 0, "issue": "..."}}], "suggestions": ["..."]}}
+```
+
+DIFF (base {base}):
+{diff}
+"""
+
+
+def gate(root, task_id, base='main', skip_review=False):
+    root = Path(root).resolve()
+    cfg, state = load(root), read_state(root)
+    task = task_by_id(cfg, task_id)
+    entry = state['tasks'].setdefault(task_id, {})
+    run_id = time.strftime('%Y%m%d-%H%M%S-') + task_id + '-' + uuid.uuid4().hex[:6]
+    evidence = root / '.loop' / 'runs' / run_id
+    evidence.mkdir(parents=True)
+    record = {'run': run_id, 'task': task_id, 'head': git(root, 'rev-parse', 'HEAD').strip(),
+              'started': time.strftime('%FT%T%z'), 'stage': None, 'errors': []}
+
+    for stage, fn in (('spec', lambda: check_spec(root, entry)),
+                      ('scope', lambda: check_scope(root, task, base)),
+                      ('clean', lambda: check_clean(root))):
+        errors = fn()
+        if errors:
+            record.update(stage=stage, errors=errors)
+            break
+    else:
+        record['checks'] = run_checks(root, task, evidence)
+        failed = [c for c in record['checks'] if c['exit'] != 0]
+        if failed:
+            record.update(stage='checks', errors=[f"{failed[0]['argv']} exited {failed[0]['exit']}; see {failed[0]['log']}"])
+        elif skip_review:
+            record.update(stage='review_skipped')
+        else:
+            try:
+                v = reviewer.review(cfg['reviewer'], root, review_prompt(root, cfg, task, base, record['checks']), evidence)
+                record['review'] = v
+                record['stage'] = 'passed' if v['verdict'] == 'pass' else 'review'
+                if v['verdict'] != 'pass':
+                    record['errors'] = [f"{b.get('file', '?')}:{b.get('line', '?')} {b.get('issue')}" for b in v['blocking']]
+            except (reviewer.ReviewError, OSError, subprocess.SubprocessError) as exc:
+                # Infrastructure failure is not a code failure: do not count it toward blocking.
+                record.update(stage='review_infra', errors=[str(exc)])
+
+    record['finished'] = time.strftime('%FT%T%z')
+    (evidence / 'result.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
+
+    if record['stage'] == 'passed':
+        entry.update(status='gate_passed', failures=[], last_pass=run_id, passed_head=record['head'])
+    elif record['stage'] in ('review_skipped', 'review_infra'):
+        entry['status'] = 'needs_review'
+    else:
+        # Progress-aware stop rule: block only on the SAME failure signature 3 times in a row.
+        sig = record['stage'] + ':' + '|'.join(sorted(record['errors']))[:500]
+        fails = entry.setdefault('failures', [])
+        fails.append(sig)
+        same = len(fails) >= MAX_SAME_FAILURE and len(set(fails[-MAX_SAME_FAILURE:])) == 1
+        entry['status'] = 'blocked' if same else 'repair'
+    entry['last_run'] = run_id
+    write_state(root, state)
+    journal(root, {'at': record['finished'], 'task': task_id, 'event': 'gate',
+                   'stage': record['stage'], 'status': entry['status'], 'run': run_id, 'head': record['head']})
+    return record, entry['status']
diff --git a/loop/reviewer.py b/loop/reviewer.py
new file mode 100644
index 0000000..06b0f8a
--- /dev/null
+++ b/loop/reviewer.py
@@ -0,0 +1,108 @@
+"""Read-only Grok reviewer via Cursor CLI, streamed with idle + total timeouts.
+
+The reviewer never gets write permission: argv containing --force/--yolo is refused,
+and Cursor runs in `--mode ask` (read-only). Its only output is a verdict we parse.
+"""
+import json
+import os
+import re
+import selectors
+import signal
+import subprocess
+import time
+from pathlib import Path
+
+FORBIDDEN = {'--force', '-f', '--yolo'}
+VERDICT_RE = re.compile(r'```json\s*(\{.*?\})\s*```', re.S)
+
+
+class ReviewError(RuntimeError):
+    pass
+
+
+def build_argv(cfg, workspace):
+    argv = list(cfg['argv']) + ['--workspace', str(workspace), '--model', cfg['model']]
+    if FORBIDDEN & set(argv):
+        raise ReviewError('Reviewer must stay read-only; remove --force/--yolo')
+    if '--mode' not in argv:
+        argv += ['--mode', 'ask']
+    return argv
+
+
+def stream(argv, prompt, cwd, out_path, idle_timeout, total_timeout):
+    """Run argv with prompt as final arg; tee stdout lines to out_path.
+
+    Kills the whole process group if no output arrives for idle_timeout seconds
+    or total_timeout is exceeded. Returns (exit_code, final_result_text).
+    """
+    p = subprocess.Popen(argv + ['--', prompt], cwd=cwd, stdin=subprocess.DEVNULL,
+                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
+                         start_new_session=True)
+    sel = selectors.DefaultSelector()
+    sel.register(p.stdout, selectors.EVENT_READ)
+    start = last = time.monotonic()
+    result, buf = None, b''
+    try:
+        with open(out_path, 'wb') as out:
+            while True:
+                now = time.monotonic()
+                if now - last > idle_timeout:
+                    raise ReviewError(f'Reviewer idle for {idle_timeout}s')
+                if now - start > total_timeout:
+                    raise ReviewError(f'Reviewer exceeded {total_timeout}s')
+                if not sel.select(timeout=1):
+                    continue
+                chunk = os.read(p.stdout.fileno(), 65536)
+                if not chunk:
+                    break
+                last = time.monotonic()
+                out.write(chunk)
+                out.flush()
+                buf += chunk
+                *lines, buf = buf.split(b'\n')
+                for line in lines:
+                    try:
+                        event = json.loads(line)
+                    except ValueError:
+                        continue
+                    if event.get('type') == 'result':
+                        if event.get('is_error'):
+                            raise ReviewError('Reviewer returned is_error')
+                        result = event.get('result', '')
+        return p.wait(timeout=10), result
+    except BaseException:
+        try:
+            os.killpg(p.pid, signal.SIGKILL)
+        except ProcessLookupError:
+            pass
+        p.wait()
+        raise
+
+
+def parse_verdict(text):
+    """Take the last ```json block; anything malformed is a failing verdict."""
+    if not text:
+        return {'verdict': 'fail', 'blocking': [{'issue': 'Reviewer produced no result'}]}
+    blocks = VERDICT_RE.findall(text)
+    try:
+        v = json.loads(blocks[-1])
+    except (IndexError, ValueError):
+        return {'verdict': 'fail', 'blocking': [{'issue': 'Reviewer verdict block missing or invalid'}]}
+    if v.get('verdict') not in ('pass', 'fail') or not isinstance(v.get('blocking', []), list):
+        return {'verdict': 'fail', 'blocking': [{'issue': f'Unrecognised verdict: {v!r}'}]}
+    v.setdefault('blocking', [])
+    v.setdefault('suggestions', [])
+    if v['blocking']:
+        v['verdict'] = 'fail'  # blocking findings always fail, whatever the label says
+    return v
+
+
+def review(cfg, workspace, prompt, evidence: Path):
+    argv = build_argv(cfg, workspace)
+    (evidence / 'review-prompt.md').write_text(prompt)
+    code, text = stream(argv, prompt, workspace, evidence / 'stream.jsonl',
+                        cfg.get('idle_timeout', 180), cfg.get('total_timeout', 1200))
+    (evidence / 'review.md').write_text(text or '')
+    if code != 0:
+        raise ReviewError(f'Reviewer exited {code}')
+    return parse_verdict(text)
diff --git a/loop/tasks.json b/loop/tasks.json
new file mode 100644
index 0000000..255ecc4
--- /dev/null
+++ b/loop/tasks.json
@@ -0,0 +1,55 @@
+{
+  "reviewer": {
+    "argv": ["cursor-agent", "--trust", "--print", "--output-format", "stream-json", "--mode", "ask"],
+    "model": "grok-4.7-high",
+    "idle_timeout": 240,
+    "total_timeout": 1500
+  },
+  "tasks": [
+    {
+      "id": "T0-loop",
+      "goal": "Loop gate itself: spec lock, scope check, clean-tree check, checks, read-only Grok review with streamed idle timeout, progress-aware blocking rule, CLI and docs.",
+      "allowed": ["loop/*", "AGENTS.md", "README.md", ".github/*", ".gitignore"],
+      "spec": ["loop/tests/test_gate.py"],
+      "checks": [["python3", "-m", "unittest", "discover", "-s", "loop/tests", "-t", "."]]
+    },
+    {
+      "id": "T1-engine",
+      "goal": "Pure domain engine (FR-01/02/03 calculation core): load seed snapshot, valuation in integer cents, concentration alerts with strict > thresholds using unrounded exact comparison, sequential buy/sell replay from the original portfolio with validation (known symbol, positive JSON integer quantity, non-negative cash, no oversell) where a failing op reports its index and leaves the last valid result unchanged, comparison of original vs simulated. Covers AC-01..AC-04 at the engine level.",
+      "allowed": ["backend/portfolio/*", "pyproject.toml", "uv.lock"],
+      "spec": ["backend/tests/test_engine.py"],
+      "checks": [["uv", "run", "--frozen", "pytest", "-q", "backend/tests/test_engine.py"]]
+    },
+    {
+      "id": "T2-api",
+      "goal": "FastAPI HTTP layer + SQLite persistence (FR-04/05): GET portfolio, POST simulate, POST/GET scenarios. Scenarios store name + snapshot id + ordered ops; reopening replays them on the backend. Clear 4xx error bodies. AC-04 over HTTP, AC-05 including a real server process restart. Original portfolio never mutated.",
+      "allowed": ["backend/portfolio/*", "pyproject.toml", "uv.lock"],
+      "spec": ["backend/tests/test_api.py", "backend/tests/test_restart.py"],
+      "checks": [["uv", "run", "--frozen", "pytest", "-q", "backend/tests"]]
+    },
+    {
+      "id": "T3-frontend",
+      "goal": "React+TypeScript UI served by the backend: overview (totals, holdings, weights, industry distribution, snapshot time, alerts with object/actual/threshold), ordered op builder, original-vs-simulated comparison, explicit loading/empty/error states, save with name, list and reopen saved scenarios. All numbers come from the backend; the UI never recomputes business values.",
+      "allowed": ["frontend/*", "backend/portfolio/*"],
+      "spec": ["e2e/flow.spec.ts"],
+      "checks": [
+        ["npm", "--prefix", "frontend", "ci"],
+        ["npm", "--prefix", "frontend", "run", "build"],
+        ["uv", "run", "--frozen", "pytest", "-q", "backend/tests"],
+        ["npm", "--prefix", "e2e", "test"]
+      ],
+      "check_timeout": 900
+    },
+    {
+      "id": "T4-delivery",
+      "goal": "Delivery: README (versions, install, init, start, URL, reopen steps), DESIGN.md (2-4 pages incl. AI collaboration record with at least one real verification), VERIFY.md (step/expected/actual/pass for AC-01..05 with screenshots), four screenshots, clean-clone install+start check script. Documents must match the actual code and loop evidence; nothing fabricated.",
+      "allowed": ["README.md", "DESIGN.md", "VERIFY.md", "docs/*", "scripts/*", "e2e/*", "Dockerfile", ".dockerignore"],
+      "spec": ["scripts/check_docs.py"],
+      "checks": [
+        ["python3", "scripts/check_docs.py"],
+        ["bash", "scripts/clean_install_check.sh"]
+      ],
+      "check_timeout": 1200
+    }
+  ]
+}
diff --git a/loop/tests/__init__.py b/loop/tests/__init__.py
new file mode 100644
index 0000000..e69de29
diff --git a/loop/tests/test_gate.py b/loop/tests/test_gate.py
new file mode 100644
index 0000000..10d6f81
--- /dev/null
+++ b/loop/tests/test_gate.py
@@ -0,0 +1,164 @@
+"""Spec for the loop gate (T0). Uses temp git repos and a fake reviewer; no network."""
+import json
+import subprocess
+import sys
+import tempfile
+import textwrap
+import unittest
+from pathlib import Path
+
+from loop import gate as g
+from loop import reviewer as r
+
+BAD_CHECK = "import pathlib, sys; sys.exit(3 if pathlib.Path('src/bad').exists() else 0)"
+
+FAKE = textwrap.dedent('''
+    import json, sys, time, os
+    mode = os.environ.get("FAKE_MODE", "pass")
+    print(json.dumps({"type": "system", "subtype": "init"}), flush=True)
+    if mode == "hang":
+        time.sleep(30)
+    verdict = {"pass": {"verdict": "pass", "blocking": [], "suggestions": ["nit"]},
+               "fail": {"verdict": "fail", "blocking": [{"file": "a.py", "line": 1, "issue": "bug"}]}}[
+        "fail" if mode == "fail" else "pass"]
+    text = "Review done.\\n```json\\n" + json.dumps(verdict) + "\\n```"
+    print(json.dumps({"type": "result", "is_error": False, "result": text}), flush=True)
+''')
+
+
+class VerdictParsing(unittest.TestCase):
+    def test_last_block_wins_and_blocking_forces_fail(self):
+        t = '```json\n{"verdict":"fail"}\n```\nlater\n```json\n{"verdict":"pass","blocking":[{"issue":"x"}]}\n```'
+        self.assertEqual(r.parse_verdict(t)['verdict'], 'fail')
+
+    def test_clean_pass(self):
+        v = r.parse_verdict('ok\n```json\n{"verdict":"pass","blocking":[]}\n```')
+        self.assertEqual((v['verdict'], v['suggestions']), ('pass', []))
+
+    def test_missing_or_garbage_is_fail(self):
+        for t in (None, '', 'looks good to me', '```json\n{nope}\n```', '```json\n{"verdict":"maybe"}\n```'):
+            self.assertEqual(r.parse_verdict(t)['verdict'], 'fail', t)
+
+
+class ReviewerSafety(unittest.TestCase):
+    def test_refuses_write_flags(self):
+        for flag in ('--force', '-f', '--yolo'):
+            with self.assertRaises(r.ReviewError):
+                r.build_argv({'argv': ['cursor-agent', flag], 'model': 'm'}, '/tmp')
+
+    def test_defaults_to_read_only_ask_mode(self):
+        argv = r.build_argv({'argv': ['cursor-agent'], 'model': 'm'}, '/tmp')
+        self.assertEqual(argv[argv.index('--mode') + 1], 'ask')
+
+
+class Streaming(unittest.TestCase):
+    def setUp(self):
+        self.tmp = Path(tempfile.mkdtemp())
+        (self.tmp / 'fake.py').write_text(FAKE)
+
+    def run_fake(self, mode, idle=5):
+        import os
+        os.environ['FAKE_MODE'] = mode
+        try:
+            return r.stream([sys.executable, str(self.tmp / 'fake.py')], 'p', self.tmp,
+                            self.tmp / 'out.jsonl', idle, 60)
+        finally:
+            del os.environ['FAKE_MODE']
+
+    def test_collects_result_and_tees_stream(self):
+        code, text = self.run_fake('pass')
+        self.assertEqual(code, 0)
+        self.assertIn('"verdict": "pass"', text)
+        self.assertIn('"type": "system"', (self.tmp / 'out.jsonl').read_text())
+
+    def test_idle_timeout_kills_reviewer(self):
+        with self.assertRaisesRegex(r.ReviewError, 'idle'):
+            self.run_fake('hang', idle=2)
+
+
+class GateFlow(unittest.TestCase):
+    """End-to-end gate behaviour in a throwaway git repository."""
+
+    def setUp(self):
+        self.root = Path(tempfile.mkdtemp())
+        sh = lambda *a: subprocess.run(a, cwd=self.root, check=True, capture_output=True)
+        self.sh = sh
+        sh('git', 'init', '-q', '-b', 'main')
+        sh('git', 'config', 'user.email', 't@t')
+        sh('git', 'config', 'user.name', 't')
+        (self.root / 'loop').mkdir()
+        (self.root / 'fake.py').write_text(FAKE)
+        (self.root / 'spec_test.py').write_text('assert True\n')
+        cfg = {'reviewer': {'argv': [sys.executable, str(self.root / 'fake.py')], 'model': 'fake',
+                            'idle_timeout': 3, 'total_timeout': 60},
+               'tasks': [{'id': 'T', 'goal': 'demo', 'allowed': ['src/*'], 'spec': ['spec_test.py'],
+                          'checks': [[sys.executable, 'spec_test.py'],
+                                     [sys.executable, '-c', BAD_CHECK]]}]}
+        (self.root / 'loop' / 'tasks.json').write_text(json.dumps(cfg))
+        (self.root / '.gitignore').write_text('.loop/\n')
+        sh('git', 'add', '-A')
+        sh('git', 'commit', '-qm', 'base')
+        sh('git', 'checkout', '-qb', 'feat')
+        g.lock_spec(self.root, 'T', 'test')
+
+    def commit(self, path, text):
+        p = self.root / path
+        p.parent.mkdir(parents=True, exist_ok=True)
+        p.write_text(text)
+        self.sh('git', 'add', '-A')
+        self.sh('git', 'commit', '-qm', path)
+
+    def test_pass_records_head_and_evidence(self):
+        self.commit('src/x.py', 'x = 1\n')
+        record, status = g.gate(self.root, 'T')
+        self.assertEqual((record['stage'], status), ('passed', 'gate_passed'))
+        state = g.read_state(self.root)['tasks']['T']
+        self.assertEqual(state['passed_head'], record['head'])
+        self.assertTrue((self.root / '.loop' / 'runs' / record['run'] / 'review.md').exists())
+
+    def test_tampered_spec_rejected_before_checks(self):
+        self.commit('spec_test.py', 'assert True  # weakened\n')
+        record, status = g.gate(self.root, 'T')
+        self.assertEqual((record['stage'], status), ('spec', 'repair'))
+        self.assertNotIn('checks', record)
+
+    def test_out_of_scope_change_rejected(self):
+        self.commit('other/y.py', 'y = 1\n')
+        self.assertEqual(g.gate(self.root, 'T')[0]['stage'], 'scope')
+
+    def test_uncommitted_work_rejected(self):
+        (self.root / 'src').mkdir()
+        (self.root / 'src' / 'x.py').write_text('dirty\n')
+        self.assertEqual(g.gate(self.root, 'T')[0]['stage'], 'clean')
+
+    def test_failing_check_skips_review(self):
+        self.commit('src/bad', 'x\n')
+        record, _ = g.gate(self.root, 'T')
+        self.assertEqual(record['stage'], 'checks')
+        self.assertEqual(record['checks'][-1]['exit'], 3)
+        self.assertNotIn('review', record)
+
+    def test_reviewer_fail_then_same_failure_three_times_blocks(self):
+        import os
+        self.commit('src/x.py', 'x = 1\n')
+        os.environ['FAKE_MODE'] = 'fail'
+        try:
+            statuses = [g.gate(self.root, 'T')[1] for _ in range(3)]
+        finally:
+            del os.environ['FAKE_MODE']
+        self.assertEqual(statuses, ['repair', 'repair', 'blocked'])
+
+    def test_reviewer_infra_failure_does_not_count_toward_block(self):
+        import os
+        self.commit('src/x.py', 'x = 1\n')
+        os.environ['FAKE_MODE'] = 'hang'
+        try:
+            record, status = g.gate(self.root, 'T')
+        finally:
+            del os.environ['FAKE_MODE']
+        self.assertEqual((record['stage'], status), ('review_infra', 'needs_review'))
+        self.assertEqual(g.read_state(self.root)['tasks']['T']['failures'], [])
+
+
+if __name__ == '__main__':
+    unittest.main()
diff --git a/tasks/todo.md b/tasks/todo.md
new file mode 100644
index 0000000..ff7bcbc
--- /dev/null
+++ b/tasks/todo.md
@@ -0,0 +1,6 @@
+# Todo
+- [ ] T0-loop：门禁 + Grok 只读审查 + CI
+- [ ] T1-engine：整数分计算核心，AC-01..04
+- [ ] T2-api：FastAPI + SQLite，AC-04 HTTP、AC-05 真重启
+- [ ] T3-frontend：React UI + e2e
+- [ ] T4-delivery：README / DESIGN / VERIFY / 截图 / 干净安装

