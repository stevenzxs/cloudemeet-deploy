import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))


class RepositoryCounterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name) / 'repo'
        root.mkdir()
        self.root = root
        self.policy = root / 'skills/full-build-deploy/config/version-policy.json'
        self.policy.parent.mkdir(parents=True)
        self.policy.write_text(json.dumps({
            'schema': 1,
            'namespace': 'cloudmeet-v1',
            'server_baseline': '11248.0.2',
            'client_baseline': '1.0.21',
            'android_base_code': 1021,
            'previous_android_code': 1021,
            'previous_msi_version': '1.0.21',
            'approved': True,
            'current_revision': 33,
        }))
        manifest = root / 'skills/full-build-deploy/inputs.sha256'
        manifest.write_text('0' * 64 + '  skills/full-build-deploy/config/version-policy.json\n')
        self.remote = Path(self.tmp.name) / 'remote.git'
        subprocess.run(['git', 'init', '--bare', str(self.remote)], check=True, capture_output=True)
        subprocess.run(['git', '-C', str(root), 'init', '-b', 'main'], check=True, capture_output=True)
        subprocess.run(['git', '-C', str(root), 'config', 'user.name', 'Fixture'], check=True)
        subprocess.run(['git', '-C', str(root), 'config', 'user.email', 'fixture@example.test'], check=True)
        subprocess.run(['git', '-C', str(root), 'add', '.'], check=True)
        subprocess.run(['git', '-C', str(root), 'commit', '-m', 'seed'], check=True, capture_output=True)
        subprocess.run(['git', '-C', str(root), 'push', str(self.remote), 'HEAD:refs/heads/main'], check=True, capture_output=True)

    def tearDown(self):
        self.tmp.cleanup()

    def request(self, run='100'):
        return {
            'repository': 'stevenzxs/cloudemeet-deploy',
            'workflow': 'joint',
            'run_id': run,
            'configuration_sha': 'a' * 40,
            'task': 'actions-' + run,
            'scope': ['server', 'h5', 'electron', 'android'],
            'sources': {'web': 'b' * 40},
        }

    def test_sequential_and_same_attempt_idempotent(self):
        from repository_counter import allocate
        first = allocate(self.policy, self.request(), attempt=1, remote=str(self.remote))
        self.assertEqual(first['versions']['revision'], 34)
        self.assertEqual(allocate(self.policy, self.request(), attempt=1, remote=str(self.remote)), first)
        second = allocate(self.policy, self.request(), attempt=2, remote=str(self.remote))
        self.assertEqual(second['versions']['revision'], 35)

    def test_concurrent_runs_get_distinct_revisions(self):
        from concurrent.futures import ThreadPoolExecutor
        from repository_counter import allocate
        with ThreadPoolExecutor(max_workers=2) as pool:
            records = list(pool.map(lambda run: allocate(self.policy, self.request(run), remote=str(self.remote)), ('200', '201')))
        self.assertEqual(sorted(record['versions']['revision'] for record in records), [34, 35])


if __name__ == '__main__':
    unittest.main()
