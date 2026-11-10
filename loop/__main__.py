"""python -m loop {status|spec|gate|mark} — see loop/README.md."""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from . import gate as g


def main(argv=None):
    p = argparse.ArgumentParser(prog='loop')
    p.add_argument('--root', type=Path, default=Path.cwd())
    sub = p.add_subparsers(dest='cmd', required=True)
    sub.add_parser('status')
    s = sub.add_parser('spec', help='lock acceptance tests for a task')
    s.add_argument('task')
    s.add_argument('--reason', default='initial spec')
    r = sub.add_parser('gate', help='spec lock → scope → clean → checks → Grok review')
    r.add_argument('task')
    r.add_argument('--base', default='main')
    r.add_argument('--skip-review', action='store_true', help='mechanical checks only; never yields a pass')
    m = sub.add_parser('mark', help='record a delivery fact, e.g. merged PR')
    m.add_argument('task')
    m.add_argument('status', choices=['pr_open', 'merged'])
    m.add_argument('--pr', required=True)
    a = p.parse_args(argv)
    root = a.root.resolve()

    if a.cmd == 'status':
        cfg, state = g.load(root), g.read_state(root)
        for t in cfg['tasks']:
            e = state['tasks'].get(t['id'], {})
            print(f"{t['id']:<16} {e.get('status', 'todo'):<13} {e.get('pr', '')}")
        return 0
    if a.cmd == 'spec':
        print(json.dumps(g.lock_spec(root, a.task, a.reason), indent=2))
        return 0
    if a.cmd == 'gate':
        record, status = g.gate(root, a.task, a.base, a.skip_review)
        print(json.dumps({'stage': record['stage'], 'status': status, 'errors': record['errors'],
                          'suggestions': record.get('review', {}).get('suggestions', []),
                          'evidence': f".loop/runs/{record['run']}"}, ensure_ascii=False, indent=2))
        return 0 if status == 'gate_passed' else 1
    if a.cmd == 'mark':
        state = g.read_state(root)
        e = state['tasks'].setdefault(a.task, {})
        if e.get('status') not in ('gate_passed', 'pr_open'):
            sys.exit('Refusing: task has not passed the gate')
        pr = json.loads(subprocess.run(['gh', 'pr', 'view', a.pr, '--json', 'headRefOid,state,url'],
                                       check=True, capture_output=True, text=True, cwd=root).stdout)
        tag = subprocess.run(['git', 'rev-parse', '--verify', '-q', f'gate/{a.task}^{{commit}}'],
                             cwd=root, capture_output=True, text=True).stdout.strip()
        if not tag or tag != e.get('passed_head'):
            sys.exit(f'Refusing: gate/{a.task} tag missing or disagrees with state; re-run the gate')
        passed = tag
        if pr['headRefOid'] != passed:
            # Allowed: commits after the pass that only add gate evidence under .loop/.
            extra = subprocess.run(['git', 'diff', '--name-status', '--no-renames', '-z',
                                    f'{passed}..{pr["headRefOid"]}'], cwd=root, capture_output=True, text=True)
            parts = [x for x in extra.stdout.split('\0') if x]
            changes = list(zip(parts[0::2], parts[1::2]))  # (status, path); deletions included
            files = [f'{st} {path}' for st, path in changes]
            if extra.returncode or not all(path.startswith('.loop/') and st in ('A', 'M') for st, path in changes):
                sys.exit(f"Refusing: PR head {pr['headRefOid'][:8]} differs from gate-passed head "
                         f"{str(passed)[:8]} beyond .loop/ evidence: {files[:5]}")
        if a.status == 'merged' and pr['state'] != 'MERGED':
            sys.exit(f"Refusing: PR state is {pr['state']}")
        a.pr = pr['url']
        e.update(status=a.status, pr=a.pr)
        g.write_state(root, state)
        g.journal(root, {'at': time.strftime('%FT%T%z'), 'task': a.task, 'event': a.status, 'pr': a.pr})
        return 0


if __name__ == '__main__':
    raise SystemExit(main())
