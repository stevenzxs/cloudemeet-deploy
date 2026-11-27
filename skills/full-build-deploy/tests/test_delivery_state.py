"""Private local state tests; no network, Docker or real deployment."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

MODULE = Path(__file__).parents[1] / 'tools' / 'delivery_state.py'


class Clock:
    def __init__(self):
        self.mono, self.wall = 100.0, 1800000000.0

    def advance(self, seconds, wall=None):
        self.mono += seconds
        self.wall += seconds if wall is None else wall


class DeliveryStateTests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'posix', 'delivery_state uses Linux/POSIX locking and permission semantics')
    def setUp(self):
        self.assertTrue(MODULE.exists(), 'Persistent delivery state is not implemented')
        spec = importlib.util.spec_from_file_location('delivery_state', MODULE)
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'state'
        self.clock = Clock()
        self.plan = [{'id': 'preflight', 'name': '核验环境'},
                     {'id': 'images', 'name': '验证镜像'}]
        self.identity = {'instance': 'example', 'scope': 'published-upgrade',
                         'configuration_sha': 'a' * 40}

    def store(self, task='task-1'):
        return self.m.TaskStore(self.root, task, monotonic=lambda: self.clock.mono,
                                wall=lambda: self.clock.wall)

    def test_immutable_plan_identity_and_numbering(self):
        original = copy.deepcopy(self.plan)
        with self.store() as s:
            s.create(self.identity, self.plan)
            self.plan[0]['id'] = 'tampered'
            view = s.view()
            self.assertEqual([x['number'] for x in view['steps']], [1, 2])
            self.assertEqual(view['plan'], original)
            view['plan'][0]['id'] = 'outside'
            self.assertEqual(s.view()['plan'], original)
            with self.assertRaises(ValueError):
                s.create(self.identity, original)

    def test_attempts_retain_time_and_retry_requires_reconciliation(self):
        with self.store() as s:
            s.create(self.identity, self.plan)
            s.transition('images', 'running')
            self.clock.advance(5)
            s.transition('images', 'failed', reason='pull_timeout')
            with self.assertRaises(ValueError):
                s.transition('images', 'running')
            s.transition('images', 'running', evidence='b' * 64)
            self.clock.advance(7)
            s.transition('images', 'succeeded', evidence='c' * 64)
            step = s.view()['steps'][1]
            self.assertEqual(step['execution_seconds'], 12)
            self.assertEqual([a['execution_seconds'] for a in step['attempts']], [5, 7])
            self.assertEqual(step['number'], 2)
            with self.assertRaises(ValueError):
                s.transition('images', 'running', evidence='c' * 64)

    def test_each_attempt_retains_outcome_reason_evidence_and_utc_boundaries(self):
        with self.store() as s:
            s.create(self.identity, self.plan)
            s.transition('images', 'running')
            self.clock.advance(2)
            s.transition('images', 'failed', reason='pull_timeout', evidence='b' * 64)
            s.transition('images', 'running', evidence='c' * 64)
            self.clock.advance(3)
            s.transition('images', 'succeeded', evidence='d' * 64)
            first, second = s.view()['steps'][1]['attempts']
            self.assertEqual(first.get('status'), 'failed')
            self.assertEqual(first.get('reason'), 'pull_timeout')
            self.assertEqual(first.get('evidence'), 'b' * 64)
            self.assertEqual(first.get('ended_utc') - first.get('started_utc'), 2)
            self.assertEqual(second.get('status'), 'succeeded')
            self.assertEqual(second.get('reconciliation_evidence'), 'c' * 64)

    def test_completed_task_query_does_not_add_post_completion_time(self):
        with self.store() as s:
            s.create(self.identity, self.plan)
            s.transition('preflight', 'not_applicable', reason='existing_batch')
            s.transition('images', 'running')
            self.clock.advance(4)
            s.transition('images', 'succeeded', evidence='b' * 64)
            self.clock.advance(100)
            s.checkpoint()
            self.assertEqual(s.view()['observed_seconds'], 4)

    def test_journal_cannot_be_rebound_by_renaming_task_directory(self):
        with self.store() as s:
            s.create(self.identity, self.plan)
        (self.root / 'task-1').rename(self.root / 'renamed')
        with self.assertRaises(ValueError):
            self.m.read_task(self.root, 'renamed')

    def test_waiting_parallel_and_backwards_wall_clock(self):
        with self.store() as s:
            s.create(self.identity, self.plan)
            s.transition('preflight', 'running')
            s.transition('images', 'running')
            self.clock.advance(5, wall=-100)
            s.transition('images', 'waiting_approval')
            self.clock.advance(3)
            s.checkpoint()
            view = s.view()
            self.assertEqual(view['observed_seconds'], 8)
            self.assertEqual(view['steps'][0]['execution_seconds'], 8)
            self.assertEqual(view['steps'][1]['execution_seconds'], 5)
            self.assertEqual(view['steps'][1]['waiting_seconds'], 3)
            self.assertTrue(view['wall_clock_uncertain'])

    def test_restart_blocks_unfinished_work_and_marks_unknown_time(self):
        with self.store() as s:
            s.create(self.identity, self.plan)
            s.transition('images', 'running')
            self.clock.advance(9)
            s.checkpoint()
        self.clock.advance(500)
        with self.store() as s:
            view = s.view()
            self.assertEqual(view['steps'][1]['status'], 'blocked')
            self.assertTrue(view['unknown_intervals'])
            self.assertEqual(view['steps'][1]['execution_seconds'], 9)
            self.assertEqual(view['observed_seconds'], 9)
            with self.assertRaises(ValueError):
                s.transition('images', 'running')

    def test_reason_evidence_and_transitions_are_validated(self):
        with self.store() as s:
            s.create(self.identity, self.plan)
            for kwargs in ({'status': 'succeeded'}, {'status': 'blocked'},
                           {'status': 'not_applicable'}, {'status': 'running', 'reason': 'token=secret'}):
                with self.assertRaises(ValueError):
                    s.transition('preflight', **kwargs)
            with self.assertRaises(ValueError):
                s.transition('missing', 'running')
            s.transition('preflight', 'not_applicable', reason='existing_batch')
            self.assertEqual(s.view()['steps'][0]['attempts'], [])
            with self.assertRaises(ValueError):
                s.transition('images', 'running', evidence='not_a_digest')

    def test_private_permissions_and_concurrent_writer_refusal(self):
        with self.store() as s:
            s.create(self.identity, self.plan)
            with self.assertRaises(BlockingIOError):
                with self.store():
                    pass
            self.assertEqual(self.root.stat().st_mode & 0o777, 0o700)
            for p in (self.root / 'task-1').iterdir():
                self.assertEqual(p.stat().st_mode & 0o777, 0o600)

    def test_read_only_query_during_writer_and_event_first_snapshot_recovery(self):
        with self.store() as s:
            s.create(self.identity, self.plan)
            s.transition('images', 'running')
            self.clock.advance(2)
            with patch.object(s, '_snapshot', side_effect=OSError('disk full')):
                with self.assertRaises(OSError):
                    s.checkpoint()
            view = self.m.read_task(self.root, 'task-1')
            self.assertEqual(view['steps'][1]['execution_seconds'], 2)
        with self.store() as s:
            self.assertEqual(s.view()['steps'][1]['execution_seconds'], 2)

    def test_corrupt_or_missing_history_never_auto_initializes(self):
        with self.store() as s:
            s.create(self.identity, self.plan)
        event = self.root / 'task-1' / '00000001.json'
        record = json.loads(event.read_text())
        record['state']['identity']['instance'] = 'changed'
        event.write_text(json.dumps(record))
        with self.assertRaises(ValueError):
            with self.store():
                pass

    def test_missing_middle_or_tail_is_detected_from_history_and_snapshot(self):
        for task, number in (('gap', 1), ('tail', 3)):
            with self.store(task) as s:
                s.create(self.identity, self.plan)
                s.transition('images', 'running')
                s.checkpoint()
            (self.root / task / f'{number:08d}.json').unlink()
            with self.assertRaises(ValueError):
                self.m.read_task(self.root, task)

    def test_stale_snapshot_and_uncommitted_temp_do_not_override_events(self):
        with self.store() as s:
            s.create(self.identity, self.plan)
            cached = (s.path / 'snapshot.json').read_bytes()
            s.transition('images', 'running')
            (s.path / 'snapshot.json').write_bytes(cached)
            (s.path / '.pending-crashed').write_text('incomplete')
            self.assertEqual(self.m.read_task(self.root, 'task-1')['steps'][1]['status'], 'running')

    def test_restart_between_steps_marks_unobserved_gap_without_running_time(self):
        with self.store() as s:
            s.create(self.identity, self.plan)
            s.transition('preflight', 'running')
            self.clock.advance(4)
            s.transition('preflight', 'succeeded', evidence='d' * 64)
        self.clock.advance(200)
        with self.store() as s:
            self.assertTrue(s.view()['unknown_intervals'])
            self.assertEqual(s.view()['observed_seconds'], 4)
            self.assertEqual(s.view()['steps'][0]['status'], 'succeeded')
            self.assertEqual(s.view()['task_id'], 'task-1')

    def test_malformed_plan_or_identity_is_rejected_without_event(self):
        for identity, plan in ((dict(self.identity, token='secret'), self.plan),
                               (dict(self.identity, configuration_sha='main'), self.plan),
                               (self.identity, self.plan + [self.plan[0]]),
                               (self.identity, [{'id': 1, 'name': 'Bad'}]),
                               (self.identity, [])):
            with self.store() as s:
                with self.assertRaises(ValueError):
                    s.create(identity, plan)
                self.assertEqual(list(s.path.glob('[0-9]*.json')), [])

    def test_closed_store_and_unsafe_event_refuse_operations(self):
        with self.store() as s:
            s.create(self.identity, self.plan)
        with self.assertRaises(ValueError):
            s.checkpoint()
        event = s.path / '00000001.json'
        event.chmod(0o644)
        with self.assertRaises(ValueError):
            self.m.read_task(self.root, 'task-1')

    def test_process_competitor_cannot_enter_while_writer_holds_lock(self):
        code = '''import importlib.util,sys
spec=importlib.util.spec_from_file_location('state',sys.argv[1])
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
try:
 with m.TaskStore(sys.argv[2],'task-1'): pass
except BlockingIOError: sys.exit(37)
'''
        with self.store() as s:
            s.create(self.identity, self.plan)
            result = subprocess.run([sys.executable, '-B', '-c', code, str(MODULE), str(self.root)],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 37, result.stderr)

    def test_rejects_repo_root_broad_permissions_symlinks_and_bad_ids(self):
        (Path(self.tmp.name) / '.git').mkdir()
        with self.assertRaises(ValueError):
            with self.store():
                pass
        (Path(self.tmp.name) / '.git').rmdir()
        self.root.mkdir(mode=0o755)
        self.root.chmod(0o755)
        with self.assertRaises(ValueError):
            with self.store():
                pass
        self.root.chmod(0o700)
        outside = Path(self.tmp.name) / 'outside'
        outside.mkdir(mode=0o700)
        (self.root / 'task-1').symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            with self.store():
                pass
        for task in ('../escape', '', 'a/b'):
            with self.assertRaises(ValueError):
                with self.store(task):
                    pass

    def test_process_death_releases_lock_and_retains_committed_checkpoint(self):
        code = '''import importlib.util,sys,os
spec=importlib.util.spec_from_file_location('state',sys.argv[1])
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
with m.TaskStore(sys.argv[2],'task-1') as s:
 s.create({'instance':'example','scope':'published-upgrade'},[{'id':'images','name':'Images'}])
 s.transition('images','running')
 s.checkpoint()
 os._exit(23)
'''
        result = subprocess.run([sys.executable, '-B', '-c', code, str(MODULE), str(self.root)],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 23, result.stderr)
        with self.store() as s:
            self.assertEqual(s.view()['steps'][0]['status'], 'blocked')
            self.assertTrue(s.view()['unknown_intervals'])


if __name__ == '__main__':
    unittest.main()
