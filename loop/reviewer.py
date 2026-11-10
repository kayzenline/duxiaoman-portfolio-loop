"""Read-only Grok reviewer via Cursor CLI, streamed with idle + total timeouts.

The reviewer never gets write permission: argv containing --force/--yolo is refused,
and Cursor runs in `--mode ask` (read-only). Its only output is a verdict we parse.
"""
import json
import os
import re
import selectors
import signal
import subprocess
import time
from pathlib import Path

FORBIDDEN = {'--force', '-f', '--yolo'}
VERDICT_RE = re.compile(r'```json\s*(\{.*?\})\s*```', re.S)


class ReviewError(RuntimeError):
    pass


def build_argv(cfg, workspace):
    argv = list(cfg['argv']) + ['--workspace', str(workspace), '--model', cfg['model']]
    if FORBIDDEN & set(argv):
        raise ReviewError('Reviewer must stay read-only; remove --force/--yolo')
    if '--mode' not in argv:
        argv += ['--mode', 'ask']
    modes = [argv[i + 1] for i, a in enumerate(argv[:-1]) if a == '--mode']
    if modes != ['ask'] or any(a.startswith('--mode=') for a in argv):
        raise ReviewError('Reviewer must run with exactly one `--mode ask`')
    return argv


def stream(argv, prompt, cwd, out_path, idle_timeout, total_timeout):
    """Run argv with prompt as final arg; tee stdout lines to out_path.

    Kills the whole process group if no output arrives for idle_timeout seconds
    or total_timeout is exceeded. Returns (exit_code, final_result_text).
    """
    p = subprocess.Popen(argv + ['--', prompt], cwd=cwd, stdin=subprocess.DEVNULL,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         start_new_session=True)
    sel = selectors.DefaultSelector()
    sel.register(p.stdout, selectors.EVENT_READ)
    start = last = time.monotonic()
    result, buf = None, b''
    def handle(line):
        nonlocal result
        try:
            event = json.loads(line)
        except ValueError:
            return
        if event.get('type') == 'result':
            if event.get('is_error'):
                raise ReviewError('Reviewer returned is_error')
            result = event.get('result', '')

    try:
        with open(out_path, 'wb') as out:
            while result is None:  # the result event is final; never let idle time discard it
                now = time.monotonic()
                if now - last > idle_timeout:
                    raise ReviewError(f'Reviewer idle for {idle_timeout}s')
                if now - start > total_timeout:
                    raise ReviewError(f'Reviewer exceeded {total_timeout}s')
                if not sel.select(timeout=1):
                    continue
                chunk = os.read(p.stdout.fileno(), 65536)
                if not chunk:
                    if buf.strip():
                        handle(buf)  # final NDJSON line without trailing newline
                    break
                last = time.monotonic()
                out.write(chunk)
                out.flush()
                buf += chunk
                *lines, buf = buf.split(b'\n')
                for line in lines:
                    handle(line)
        if result is not None and p.poll() is None:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid, signal.SIGKILL)  # verdict already captured; reap a lingering CLI
                p.wait()
            return 0, result
        return p.wait(timeout=10), result
    except BaseException:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        p.wait()
        raise


def parse_verdict(text):
    """Take the last ```json block; anything malformed is a failing verdict."""
    if not text:
        return {'verdict': 'fail', 'blocking': [{'issue': 'Reviewer produced no result'}]}
    blocks = VERDICT_RE.findall(text)
    try:
        v = json.loads(blocks[-1])
    except (IndexError, ValueError):
        return {'verdict': 'fail', 'blocking': [{'issue': 'Reviewer verdict block missing or invalid'}]}
    if v.get('verdict') not in ('pass', 'fail') or not isinstance(v.get('blocking', []), list):
        return {'verdict': 'fail', 'blocking': [{'issue': f'Unrecognised verdict: {v!r}'}]}
    if not all(isinstance(b, dict) for b in v.get('blocking', [])):
        return {'verdict': 'fail', 'blocking': [{'issue': 'Malformed blocking entries in verdict'}], 'suggestions': []}
    v.setdefault('blocking', [])
    v.setdefault('suggestions', [])
    if v['blocking']:
        v['verdict'] = 'fail'  # blocking findings always fail, whatever the label says
    return v


def review(cfg, workspace, prompt, evidence: Path):
    argv = build_argv(cfg, workspace)
    (evidence / 'review-prompt.md').write_text(prompt)
    code, text = stream(argv, prompt, workspace, evidence / 'stream.jsonl',
                        cfg.get('idle_timeout', 180), cfg.get('total_timeout', 1200))
    (evidence / 'review.md').write_text(text or '')
    if code != 0:
        raise ReviewError(f'Reviewer exited {code}')
    return parse_verdict(text)
