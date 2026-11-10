"""Spec for the loop gate (T0). Uses temp git repos and a fake reviewer; no network."""
import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from loop import gate as g
from loop import reviewer as r

BAD_CHECK = "import pathlib, sys; sys.exit(3 if pathlib.Path('src/bad').exists() else 0)"

FAKE = textwrap.dedent('''
    import json, sys, time, os
    mode = os.environ.get("FAKE_MODE", "pass")
    print(json.dumps({"type": "system", "subtype": "init"}), flush=True)
    if mode == "hang":
        time.sleep(30)
    verdict = {"pass": {"verdict": "pass", "blocking": [], "suggestions": ["nit"]},
               "fail": {"verdict": "fail", "blocking": [{"file": "a.py", "line": 1, "issue": "bug"}]}}[
        "fail" if mode == "fail" else "pass"]
    text = "Review done.\\n```json\\n" + json.dumps(verdict) + "\\n```"
    print(json.dumps({"type": "result", "is_error": False, "result": text}), flush=True)
''')


class VerdictParsing(unittest.TestCase):
    def test_last_block_wins_and_blocking_forces_fail(self):
        t = '```json\n{"verdict":"fail"}\n```\nlater\n```json\n{"verdict":"pass","blocking":[{"issue":"x"}]}\n```'
        self.assertEqual(r.parse_verdict(t)['verdict'], 'fail')

    def test_clean_pass(self):
        v = r.parse_verdict('ok\n```json\n{"verdict":"pass","blocking":[]}\n```')
        self.assertEqual((v['verdict'], v['suggestions']), ('pass', []))

    def test_missing_or_garbage_is_fail(self):
        for t in (None, '', 'looks good to me', '```json\n{nope}\n```', '```json\n{"verdict":"maybe"}\n```'):
            self.assertEqual(r.parse_verdict(t)['verdict'], 'fail', t)


class ReviewerSafety(unittest.TestCase):
    def test_refuses_write_flags(self):
        for flag in ('--force', '-f', '--yolo'):
            with self.assertRaises(r.ReviewError):
                r.build_argv({'argv': ['cursor-agent', flag], 'model': 'm'}, '/tmp')

    def test_defaults_to_read_only_ask_mode(self):
        argv = r.build_argv({'argv': ['cursor-agent'], 'model': 'm'}, '/tmp')
        self.assertEqual(argv[argv.index('--mode') + 1], 'ask')


class Streaming(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / 'fake.py').write_text(FAKE)

    def run_fake(self, mode, idle=5):
        import os
        os.environ['FAKE_MODE'] = mode
        try:
            return r.stream([sys.executable, str(self.tmp / 'fake.py')], 'p', self.tmp,
                            self.tmp / 'out.jsonl', idle, 60)
        finally:
            del os.environ['FAKE_MODE']

    def test_collects_result_and_tees_stream(self):
        code, text = self.run_fake('pass')
        self.assertEqual(code, 0)
        self.assertIn('"verdict": "pass"', text)
        self.assertIn('"type": "system"', (self.tmp / 'out.jsonl').read_text())

    def test_idle_timeout_kills_reviewer(self):
        with self.assertRaisesRegex(r.ReviewError, 'idle'):
            self.run_fake('hang', idle=2)


class GateFlow(unittest.TestCase):
    """End-to-end gate behaviour in a throwaway git repository."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        sh = lambda *a: subprocess.run(a, cwd=self.root, check=True, capture_output=True)
        self.sh = sh
        sh('git', 'init', '-q', '-b', 'main')
        sh('git', 'config', 'user.email', 't@t')
        sh('git', 'config', 'user.name', 't')
        (self.root / 'loop').mkdir()
        (self.root / 'fake.py').write_text(FAKE)
        (self.root / 'spec_test.py').write_text('assert True\n')
        cfg = {'reviewer': {'argv': [sys.executable, str(self.root / 'fake.py')], 'model': 'fake',
                            'idle_timeout': 3, 'total_timeout': 60},
               'tasks': [{'id': 'T', 'goal': 'demo', 'allowed': ['src/*'], 'spec': ['spec_test.py'],
                          'checks': [[sys.executable, 'spec_test.py'],
                                     [sys.executable, '-c', BAD_CHECK]]}]}
        (self.root / 'loop' / 'tasks.json').write_text(json.dumps(cfg))
        (self.root / '.gitignore').write_text('.loop/\n')
        sh('git', 'add', '-A')
        sh('git', 'commit', '-qm', 'base')
        sh('git', 'checkout', '-qb', 'feat')
        g.lock_spec(self.root, 'T', 'test')

    def commit(self, path, text):
        p = self.root / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        self.sh('git', 'add', '-A')
        self.sh('git', 'commit', '-qm', path)

    def test_pass_records_head_and_evidence(self):
        self.commit('src/x.py', 'x = 1\n')
        record, status = g.gate(self.root, 'T')
        self.assertEqual((record['stage'], status), ('passed', 'gate_passed'))
        state = g.read_state(self.root)['tasks']['T']
        self.assertEqual(state['passed_head'], record['head'])
        self.assertTrue((self.root / '.loop' / 'runs' / record['run'] / 'review.md').exists())

    def test_tampered_spec_rejected_before_checks(self):
        self.commit('spec_test.py', 'assert True  # weakened\n')
        record, status = g.gate(self.root, 'T')
        self.assertEqual((record['stage'], status), ('spec', 'repair'))
        self.assertNotIn('checks', record)

    def test_out_of_scope_change_rejected(self):
        self.commit('other/y.py', 'y = 1\n')
        self.assertEqual(g.gate(self.root, 'T')[0]['stage'], 'scope')

    def test_uncommitted_work_rejected(self):
        (self.root / 'src').mkdir()
        (self.root / 'src' / 'x.py').write_text('dirty\n')
        self.assertEqual(g.gate(self.root, 'T')[0]['stage'], 'clean')

    def test_failing_check_skips_review(self):
        self.commit('src/bad', 'x\n')
        record, _ = g.gate(self.root, 'T')
        self.assertEqual(record['stage'], 'checks')
        self.assertEqual(record['checks'][-1]['exit'], 3)
        self.assertNotIn('review', record)

    def test_reviewer_fail_then_same_failure_three_times_blocks(self):
        import os
        self.commit('src/x.py', 'x = 1\n')
        os.environ['FAKE_MODE'] = 'fail'
        try:
            statuses = [g.gate(self.root, 'T')[1] for _ in range(3)]
        finally:
            del os.environ['FAKE_MODE']
        self.assertEqual(statuses, ['repair', 'repair', 'blocked'])

    def test_reviewer_infra_failure_does_not_count_toward_block(self):
        import os
        self.commit('src/x.py', 'x = 1\n')
        os.environ['FAKE_MODE'] = 'hang'
        try:
            record, status = g.gate(self.root, 'T')
        finally:
            del os.environ['FAKE_MODE']
        self.assertEqual((record['stage'], status), ('review_infra', 'needs_review'))
        self.assertEqual(g.read_state(self.root)['tasks']['T']['failures'], [])


if __name__ == '__main__':
    unittest.main()
