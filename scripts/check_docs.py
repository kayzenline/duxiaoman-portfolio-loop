"""T4 acceptance spec: delivery materials exist, are complete, and cite real evidence.

Checks are structural and anti-fabrication; they cannot judge prose quality (Grok review does).
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIRST_COMMIT_PLAN = 'docs: initial PLAN and original assessment materials'
errors = []


def need(cond, msg):
    if not cond:
        errors.append(msg)


def text(name):
    p = ROOT / name
    need(p.exists(), f'{name} missing')
    return p.read_text(encoding='utf-8') if p.exists() else ''


def git(*a):
    return subprocess.run(['git', *a], cwd=ROOT, capture_output=True, text=True).stdout.strip()


# PLAN.md is the original first-commit version, never rewritten (task §3.1)
first = git('log', '--format=%H', '--grep', FIRST_COMMIT_PLAN, '--', 'PLAN.md').splitlines()
need(first, 'cannot find the initial PLAN commit')
if first:
    need(git('diff', first[-1], 'HEAD', '--', 'PLAN.md') == '', 'PLAN.md changed after its initial commit')
need(len(text('PLAN.md').splitlines()) <= 40, 'PLAN.md longer than one page')

readme = text('README.md')
for item in ['Python', 'Node', 'uv sync', 'npm', 'http://127.0.0.1:8000', '重开', 'PORTFOLIO_DB']:
    need(item in readme, f'README.md lacks {item!r}')

design = text('DESIGN.md')
for heading in ['需求与交互', '数据与状态', '系统结构与接口', '计算与异常', '设计决策', '完成情况与复盘', 'AI 协作记录']:
    need(re.search(rf'^#+ .*{heading}', design, re.M), f'DESIGN.md lacks section {heading}')
for topic in ['加载', '空方案', '失败', '价格缺失', '行业未知', '一小时']:
    need(topic in design, f'DESIGN.md does not discuss {topic}')
need(design.count('备选') >= 2, 'DESIGN.md should record at least two decisions with alternatives (备选)')
# every loop run cited in docs must exist with a result.json (no invented evidence)
cited = set(re.findall(r'\.loop/runs/([\w.-]+)', design + text('VERIFY.md')))
need(cited, 'DESIGN/VERIFY cite no .loop/runs evidence')
for run in cited:
    need((ROOT / '.loop/runs' / run / 'result.json').exists(), f'cited run {run} has no result.json')

verify = text('VERIFY.md')
for ac in ['AC-01', 'AC-02', 'AC-03', 'AC-04', 'AC-05']:
    row = [line for line in verify.splitlines() if line.startswith('|') and ac in line]
    need(row, f'VERIFY.md has no table row for {ac}')
    need(any('通过' in r for r in row), f'VERIFY.md row for {ac} is not marked 通过')
for shot in ['01-initial', '02-compare', '03-error', '04-saved']:
    p = ROOT / 'docs' / 'screenshots' / f'{shot}.png'
    need(p.exists() and p.read_bytes()[:8] == b'\x89PNG\r\n\x1a\n', f'screenshot {shot}.png missing or not a PNG')
    need(f'{shot}.png' in verify, f'VERIFY.md does not reference {shot}.png')
need('实际投入' in readme + verify + design, 'actual time spent not stated')
need('未完成' in readme + verify + design, 'unfinished items not stated')

# no secrets or dependency dirs committed
tracked = git('ls-files').splitlines()
need(not [f for f in tracked if f.startswith(('node_modules/', '.venv/')) or '/node_modules/' in f],
     'dependency directories are tracked')
need(not [f for f in tracked if re.search(r'(\.env$|\.pem$|id_rsa)', f)], 'secret-like files are tracked')
for lock in ['uv.lock', 'frontend/package-lock.json', 'e2e/package-lock.json']:
    need(lock in tracked, f'{lock} not tracked')

print(json.dumps({'ok': not errors, 'errors': errors}, ensure_ascii=False, indent=2))
sys.exit(1 if errors else 0)
