"""Gate: the only path from "implemented" to "mergeable".

Order (cheap → expensive): spec lock → scope → checks → Grok review.
State lives in the repo (.loop/state.json); evidence in .loop/runs/<run>/.
"""
import fnmatch
import hashlib
import json
import os
import subprocess
import time
import uuid
from pathlib import Path

from . import reviewer

ALWAYS_ALLOWED = ['.loop/*', 'tasks/*']
MAX_SAME_FAILURE = 3
DIFF_LIMIT = 60_000


def load(root):
    return json.loads((root / 'loop' / 'tasks.json').read_text())


def task_by_id(cfg, task_id):
    for t in cfg['tasks']:
        if t['id'] == task_id:
            return t
    raise SystemExit(f'Unknown task {task_id}')


def read_state(root):
    p = root / '.loop' / 'state.json'
    return json.loads(p.read_text()) if p.exists() else {'version': 2, 'tasks': {}}


def write_state(root, state):
    p = root / '.loop' / 'state.json'
    p.parent.mkdir(exist_ok=True)
    tmp = p.with_suffix('.tmp')
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n')
    os.replace(tmp, p)


def journal(root, entry):
    with (root / '.loop' / 'journal.jsonl').open('a') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + '\n')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(root, *args):
    return subprocess.run(['git', *args], cwd=root, check=True,
                          capture_output=True, text=True).stdout


def changed_files(root, base):
    committed = git(root, 'diff', '--name-only', f'{base}...HEAD').split()
    dirty = [line[3:].split(' -> ')[-1] for line in git(root, 'status', '--porcelain').splitlines()]
    return sorted(set(committed + dirty))


def lock_spec(root, task_id, reason):
    """Record hashes of the task's acceptance tests. Re-locking is explicit and journaled."""
    cfg, state = load(root), read_state(root)
    t = task_by_id(cfg, task_id)
    hashes = {s: sha(root / s) for s in t['spec']}
    entry = state['tasks'].setdefault(task_id, {})
    relock = 'spec' in entry
    entry.update(spec=hashes, status='spec_locked', failures=[])
    write_state(root, state)
    journal(root, {'at': time.strftime('%FT%T%z'), 'task': task_id,
                   'event': 'spec_relocked' if relock else 'spec_locked', 'reason': reason, 'spec': hashes})
    return hashes


def check_spec(root, entry):
    errors = []
    for path, digest in entry.get('spec', {}).items():
        p = root / path
        if not p.exists() or sha(p) != digest:
            errors.append(f'Acceptance test changed or missing since lock: {path}')
    if not entry.get('spec'):
        errors.append('Spec not locked; run `python -m loop spec <task>` first')
    return errors


def check_scope(root, task, base):
    allowed = task['allowed'] + task['spec'] + ALWAYS_ALLOWED
    return [f'Out of scope change: {f}' for f in changed_files(root, base)
            if not any(fnmatch.fnmatch(f, pat) for pat in allowed)]


def check_clean(root):
    """A pass must describe a commit, so uncommitted work (outside .loop/) is rejected."""
    dirty = [line[3:] for line in git(root, 'status', '--porcelain').splitlines()
             if not line[3:].startswith('.loop/')]
    return [f'Uncommitted change, commit before gating: {f}' for f in dirty]


def run_checks(root, task, evidence):
    results = []
    for i, argv in enumerate(task['checks']):
        log = evidence / f'check-{i}.log'
        t0 = time.monotonic()
        try:
            with log.open('w') as out:
                code = subprocess.run(argv, cwd=root, stdout=out, stderr=subprocess.STDOUT,
                                      timeout=task.get('check_timeout', 600)).returncode
        except subprocess.TimeoutExpired:
            code = 'timeout'
        results.append({'argv': argv, 'exit': code, 'seconds': round(time.monotonic() - t0, 1),
                        'log': str(log.relative_to(root))})
        if code != 0:
            break
    return results


def review_prompt(root, cfg, task, base, checks):
    diff = git(root, 'diff', f'{base}...HEAD') + git(root, 'diff', 'HEAD')
    if len(diff) > DIFF_LIMIT:
        diff = diff[:DIFF_LIMIT] + '\n[diff truncated; read the files directly]'
    return f"""You are the independent code reviewer for a take-home assessment repository.
Another agent (Claude Code) implemented this change; you did not write it. Review it critically.

Requirements source of truth: context/originals/投资组合示例数据.json and context/BRIEF.md
(summary of the task PDF, which is at context/originals/度小满_全栈开发实习_技术测评任务.pdf).
Read the actual files in the workspace as needed; do not trust this prompt's summary of them.

Task `{task['id']}`: {task['goal']}
Acceptance tests (locked; implementer may not edit): {', '.join(task['spec'])}
Files the implementer was allowed to change: {', '.join(task['allowed'])}
Mechanical checks already run by the gate (all exit 0): {json.dumps([c['argv'] for c in checks])}

Focus: requirement mismatches, wrong business rules (strict > thresholds, cash in denominator, integer quantities,
failed ops must not change valid results, isolation of original portfolio), precision bugs, missing error handling,
tests that pass without proving the requirement, security issues. Ignore pure style.
Only mark something blocking if it violates a requirement or is a real bug; put preferences in suggestions.

End your answer with exactly one fenced json block of this shape:
```json
{{"verdict": "pass or fail", "blocking": [{{"file": "path", "line": 0, "issue": "..."}}], "suggestions": ["..."]}}
```

DIFF (base {base}):
{diff}
"""


def gate(root, task_id, base='main', skip_review=False):
    root = Path(root).resolve()
    cfg, state = load(root), read_state(root)
    task = task_by_id(cfg, task_id)
    entry = state['tasks'].setdefault(task_id, {})
    run_id = time.strftime('%Y%m%d-%H%M%S-') + task_id + '-' + uuid.uuid4().hex[:6]
    evidence = root / '.loop' / 'runs' / run_id
    evidence.mkdir(parents=True)
    record = {'run': run_id, 'task': task_id, 'head': git(root, 'rev-parse', 'HEAD').strip(),
              'started': time.strftime('%FT%T%z'), 'stage': None, 'errors': []}

    for stage, fn in (('spec', lambda: check_spec(root, entry)),
                      ('scope', lambda: check_scope(root, task, base)),
                      ('clean', lambda: check_clean(root))):
        errors = fn()
        if errors:
            record.update(stage=stage, errors=errors)
            break
    else:
        record['checks'] = run_checks(root, task, evidence)
        failed = [c for c in record['checks'] if c['exit'] != 0]
        if failed:
            record.update(stage='checks', errors=[f"{failed[0]['argv']} exited {failed[0]['exit']}; see {failed[0]['log']}"])
        elif skip_review:
            record.update(stage='review_skipped')
        else:
            try:
                v = reviewer.review(cfg['reviewer'], root, review_prompt(root, cfg, task, base, record['checks']), evidence)
                record['review'] = v
                record['stage'] = 'passed' if v['verdict'] == 'pass' else 'review'
                if v['verdict'] != 'pass':
                    record['errors'] = [f"{b.get('file', '?')}:{b.get('line', '?')} {b.get('issue')}" for b in v['blocking']]
            except (reviewer.ReviewError, OSError, subprocess.SubprocessError) as exc:
                # Infrastructure failure is not a code failure: do not count it toward blocking.
                record.update(stage='review_infra', errors=[str(exc)])

    record['finished'] = time.strftime('%FT%T%z')
    (evidence / 'result.json').write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')

    if record['stage'] == 'passed':
        entry.update(status='gate_passed', failures=[], last_pass=run_id, passed_head=record['head'])
    elif record['stage'] in ('review_skipped', 'review_infra'):
        entry['status'] = 'needs_review'
    else:
        # Progress-aware stop rule: block only on the SAME failure signature 3 times in a row.
        sig = record['stage'] + ':' + '|'.join(sorted(record['errors']))[:500]
        fails = entry.setdefault('failures', [])
        fails.append(sig)
        same = len(fails) >= MAX_SAME_FAILURE and len(set(fails[-MAX_SAME_FAILURE:])) == 1
        entry['status'] = 'blocked' if same else 'repair'
    entry['last_run'] = run_id
    write_state(root, state)
    journal(root, {'at': record['finished'], 'task': task_id, 'event': 'gate',
                   'stage': record['stage'], 'status': entry['status'], 'run': run_id, 'head': record['head']})
    return record, entry['status']
