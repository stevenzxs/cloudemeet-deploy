import json
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'versioning'))
import revision_versions
import repository_counter


class AndroidRevisionVersionTests(unittest.TestCase):
    def policy(self):
        return json.loads((ROOT / 'config/version-policy.json').read_text(encoding='utf-8'))

    def test_policy_starts_after_existing_shared_high_water_mark(self):
        policy = self.policy()
        self.assertEqual(policy['current_revision'], 63)
        self.assertEqual(policy['android_base_code'], 1021)
        self.assertEqual(policy['namespace'], 'cloudmeet-android-v1')

    def test_revision_64_uses_approved_android_formula(self):
        result = revision_versions.derive(self.policy(), 64)
        self.assertEqual(result, {'revision': 64, 'server_version': '11248.0.1+r64',
                                  'server_tag': '11248.0.1-r64', 'client_version': '1.0.21+r64',
                                  'android_code': 1021640, 'msi_version': '1.0.850',
                                  'pe_version': '1.0.850.0', 'version_formula': 2})

    def test_rejects_invalid_revision_or_unapproved_policy(self):
        with self.assertRaises(ValueError):
            revision_versions.derive(self.policy(), 0)
        with self.assertRaises(ValueError):
            revision_versions.derive(dict(self.policy(), approved=False), 64)

    def test_allocate_starts_at_64_and_is_idempotent_for_same_run_attempt(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'repo'
            policy_path = root / 'skills/android-build-deploy/config/version-policy.json'
            policy_path.parent.mkdir(parents=True)
            policy_path.write_text(json.dumps(self.policy()), encoding='utf-8')
            remote = Path(temp) / 'remote.git'
            subprocess.run(['git', 'init', '--bare', str(remote)], check=True, capture_output=True)
            subprocess.run(['git', '-C', str(root), 'init', '-b', 'main'], check=True, capture_output=True)
            subprocess.run(['git', '-C', str(root), 'config', 'user.name', 'Fixture'], check=True)
            subprocess.run(['git', '-C', str(root), 'config', 'user.email', 'fixture@example.test'], check=True)
            subprocess.run(['git', '-C', str(root), 'add', '.'], check=True)
            subprocess.run(['git', '-C', str(root), 'commit', '-m', 'seed'], check=True, capture_output=True)
            subprocess.run(['git', '-C', str(root), 'push', str(remote), 'HEAD:refs/heads/main'], check=True, capture_output=True)
            request = {'repository': 'stevenzxs/cloudemeet-deploy', 'workflow': 'build-android.yml',
                       'run_id': '100', 'configuration_sha': 'a' * 40, 'task': 'actions-100',
                       'scope': ['android'], 'sources': {'android': 'b' * 40, 'electron': 'c' * 40, 'server': 'd' * 40}}
            first = repository_counter.allocate(policy_path, request, remote=str(remote))
            self.assertEqual(first['versions']['revision'], 64)
            self.assertEqual(repository_counter.allocate(policy_path, request, remote=str(remote)), first)

    def test_allocate_refuses_same_run_with_changed_request(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'repo'
            policy_path = root / 'skills/android-build-deploy/config/version-policy.json'
            policy_path.parent.mkdir(parents=True)
            policy_path.write_text(json.dumps(self.policy()), encoding='utf-8')
            remote = Path(temp) / 'remote.git'
            subprocess.run(['git', 'init', '--bare', str(remote)], check=True, capture_output=True)
            subprocess.run(['git', '-C', str(root), 'init', '-b', 'main'], check=True, capture_output=True)
            subprocess.run(['git', '-C', str(root), 'config', 'user.name', 'Fixture'], check=True)
            subprocess.run(['git', '-C', str(root), 'config', 'user.email', 'fixture@example.test'], check=True)
            subprocess.run(['git', '-C', str(root), 'add', '.'], check=True)
            subprocess.run(['git', '-C', str(root), 'commit', '-m', 'seed'], check=True, capture_output=True)
            subprocess.run(['git', '-C', str(root), 'push', str(remote), 'HEAD:refs/heads/main'], check=True, capture_output=True)
            request = {'repository': 'stevenzxs/cloudemeet-deploy', 'workflow': 'build-android.yml',
                       'run_id': '100', 'configuration_sha': 'a' * 40, 'task': 'actions-100',
                       'scope': ['android'], 'sources': {'android': 'b' * 40, 'electron': 'c' * 40, 'server': 'd' * 40}}
            repository_counter.allocate(policy_path, request, remote=str(remote))
            with self.assertRaisesRegex(ValueError, 'different request'):
                repository_counter.allocate(policy_path, dict(request, configuration_sha='c' * 40), remote=str(remote))

    def test_concurrent_allocations_get_distinct_revisions(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'repo'
            policy_path = root / 'skills/android-build-deploy/config/version-policy.json'
            policy_path.parent.mkdir(parents=True)
            policy_path.write_text(json.dumps(self.policy()), encoding='utf-8')
            remote = Path(temp) / 'remote.git'
            subprocess.run(['git', 'init', '--bare', str(remote)], check=True, capture_output=True)
            subprocess.run(['git', '-C', str(root), 'init', '-b', 'main'], check=True, capture_output=True)
            subprocess.run(['git', '-C', str(root), 'config', 'user.name', 'Fixture'], check=True)
            subprocess.run(['git', '-C', str(root), 'config', 'user.email', 'fixture@example.test'], check=True)
            subprocess.run(['git', '-C', str(root), 'add', '.'], check=True)
            subprocess.run(['git', '-C', str(root), 'commit', '-m', 'seed'], check=True, capture_output=True)
            subprocess.run(['git', '-C', str(root), 'push', str(remote), 'HEAD:refs/heads/main'], check=True, capture_output=True)

            def allocate(run_id):
                request = {'repository': 'stevenzxs/cloudemeet-deploy', 'workflow': 'build-android.yml',
                           'run_id': run_id, 'configuration_sha': 'a' * 40, 'task': f'actions-{run_id}',
                           'scope': ['android'], 'sources': {'android': 'b' * 40, 'electron': 'c' * 40, 'server': 'd' * 40}}
                return repository_counter.allocate(policy_path, request, remote=str(remote))

            with ThreadPoolExecutor(max_workers=2) as pool:
                records = list(pool.map(allocate, ['200', '201']))
            self.assertEqual(sorted(item['versions']['revision'] for item in records), [64, 65])

    def test_missing_or_corrupt_policy_is_not_bootstrapped(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'repo'
            policy_path = root / 'skills/android-build-deploy/config/version-policy.json'
            policy_path.parent.mkdir(parents=True)
            policy_path.write_text('{bad json', encoding='utf-8')
            remote = Path(temp) / 'remote.git'
            subprocess.run(['git', 'init', '--bare', str(remote)], check=True, capture_output=True)
            subprocess.run(['git', '-C', str(root), 'init', '-b', 'main'], check=True, capture_output=True)
            subprocess.run(['git', '-C', str(root), 'config', 'user.name', 'Fixture'], check=True)
            subprocess.run(['git', '-C', str(root), 'config', 'user.email', 'fixture@example.test'], check=True)
            subprocess.run(['git', '-C', str(root), 'add', '.'], check=True)
            subprocess.run(['git', '-C', str(root), 'commit', '-m', 'seed'], check=True, capture_output=True)
            subprocess.run(['git', '-C', str(root), 'push', str(remote), 'HEAD:refs/heads/main'], check=True, capture_output=True)
            request = {'repository': 'stevenzxs/cloudemeet-deploy', 'workflow': 'build-android.yml',
                       'run_id': '300', 'configuration_sha': 'a' * 40, 'task': 'actions-300',
                       'scope': ['android'], 'sources': {'android': 'b' * 40, 'electron': 'c' * 40, 'server': 'd' * 40}}
            with self.assertRaises(json.JSONDecodeError):
                repository_counter.allocate(policy_path, request, remote=str(remote))

    def test_changed_attempt_material_is_rejected_and_new_attempt_allocates_next_revision(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'repo'
            policy_path = root / 'skills/android-build-deploy/config/version-policy.json'
            policy_path.parent.mkdir(parents=True)
            policy_path.write_text(json.dumps(self.policy()), encoding='utf-8')
            remote = Path(temp) / 'remote.git'
            subprocess.run(['git', 'init', '--bare', str(remote)], check=True, capture_output=True)
            subprocess.run(['git', '-C', str(root), 'init', '-b', 'main'], check=True, capture_output=True)
            subprocess.run(['git', '-C', str(root), 'config', 'user.name', 'Fixture'], check=True)
            subprocess.run(['git', '-C', str(root), 'config', 'user.email', 'fixture@example.test'], check=True)
            subprocess.run(['git', '-C', str(root), 'add', '.'], check=True)
            subprocess.run(['git', '-C', str(root), 'commit', '-m', 'seed'], check=True, capture_output=True)
            subprocess.run(['git', '-C', str(root), 'push', str(remote), 'HEAD:refs/heads/main'], check=True, capture_output=True)
            request = {'repository': 'stevenzxs/cloudemeet-deploy', 'workflow': 'build-android.yml',
                       'run_id': '100', 'configuration_sha': 'a' * 40, 'task': 'actions-100',
                       'scope': ['android'], 'sources': {'android': 'b' * 40, 'electron': 'c' * 40, 'server': 'd' * 40}}
            repository_counter.allocate(policy_path, request, attempt=1, remote=str(remote))
            with self.assertRaisesRegex(ValueError, 'different request'):
                repository_counter.allocate(policy_path, dict(request, configuration_sha='c' * 40), attempt=1, remote=str(remote))
            second = repository_counter.allocate(policy_path, dict(request, configuration_sha='c' * 40), attempt=2, remote=str(remote))
            self.assertEqual(second['versions']['revision'], 65)

    def test_revisions_are_isolated_between_platform_policy_paths(self):
        self.assertNotEqual(repository_counter.POLICY_REL, Path('skills/msi-build-deploy/config/version-policy.json'))
        self.assertNotEqual(repository_counter.POLICY_REL, Path('skills/server-build-deploy/config/version-policy.json'))

    def test_allocation_identity_uses_only_android_material_pin(self):
        request = {'repository': 'stevenzxs/cloudemeet-deploy', 'workflow': 'build-android.yml',
                   'run_id': '1', 'configuration_sha': 'a' * 40, 'task': 'actions-1',
                   'scope': ['android'], 'sources': {'android': 'b' * 40}}
        repository_counter._validate_request(request)

    def test_rejects_non_monotonic_policy_revision(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'repo'
            path = root / 'skills/android-build-deploy/config/version-policy.json'
            path.parent.mkdir(parents=True)
            policy = self.policy()
            policy['current_revision'] = 62
            path.write_text(json.dumps(policy), encoding='utf-8')
            subprocess.run(['git', '-C', str(root), 'init', '-b', 'main'], check=True, capture_output=True)
            subprocess.run(['git', '-C', str(root), 'config', 'user.name', 'Fixture'], check=True)
            subprocess.run(['git', '-C', str(root), 'config', 'user.email', 'fixture@example.test'], check=True)
            subprocess.run(['git', '-C', str(root), 'add', '.'], check=True)
            subprocess.run(['git', '-C', str(root), 'commit', '-m', 'seed'], check=True, capture_output=True)
            remote = Path(temp) / 'remote.git'
            subprocess.run(['git', 'init', '--bare', str(remote)], check=True, capture_output=True)
            subprocess.run(['git', '-C', str(root), 'push', str(remote), 'HEAD:refs/heads/main'], check=True, capture_output=True)
            request = {'repository': 'stevenzxs/cloudemeet-deploy', 'workflow': 'build-android.yml',
                       'run_id': '301', 'configuration_sha': 'a' * 40, 'task': 'actions-301',
                       'scope': ['android'], 'sources': {'android': 'b' * 40}}
            with self.assertRaisesRegex(ValueError, 'current_revision'):
                repository_counter.allocate(path, request, remote=str(remote))

    def test_allocator_commit_changes_only_android_policy(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'repo'
            path = root / 'skills/android-build-deploy/config/version-policy.json'
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(self.policy()), encoding='utf-8')
            (root / 'skills/msi-build-deploy/config').mkdir(parents=True)
            (root / 'skills/msi-build-deploy/config/version-policy.json').write_text('{"current_revision":63}', encoding='utf-8')
            remote = Path(temp) / 'remote.git'
            subprocess.run(['git', 'init', '--bare', str(remote)], check=True, capture_output=True)
            subprocess.run(['git', '-C', str(root), 'init', '-b', 'main'], check=True, capture_output=True)
            subprocess.run(['git', '-C', str(root), 'config', 'user.name', 'Fixture'], check=True)
            subprocess.run(['git', '-C', str(root), 'config', 'user.email', 'fixture@example.test'], check=True)
            subprocess.run(['git', '-C', str(root), 'add', '.'], check=True)
            subprocess.run(['git', '-C', str(root), 'commit', '-m', 'seed'], check=True, capture_output=True)
            subprocess.run(['git', '-C', str(root), 'push', str(remote), 'HEAD:refs/heads/main'], check=True, capture_output=True)
            request = {'repository': 'stevenzxs/cloudemeet-deploy', 'workflow': 'build-android.yml',
                       'run_id': '400', 'configuration_sha': 'a' * 40, 'task': 'actions-400',
                       'scope': ['android'], 'sources': {'android': 'b' * 40}}
            repository_counter.allocate(path, request, remote=str(remote))
            changed = subprocess.check_output(['git', '--git-dir', str(remote), 'diff-tree', '--no-commit-id', '--name-only', '-r', 'main'], text=True).splitlines()
            self.assertEqual(changed, ['skills/android-build-deploy/config/version-policy.json'])

    def test_rejects_a_path_outside_android_owned_policy(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'repo'
            other = root / 'skills/msi-build-deploy/config/version-policy.json'
            other.parent.mkdir(parents=True)
            other.write_text('{}', encoding='utf-8')
            subprocess.run(['git', '-C', str(root), 'init', '-b', 'main'], check=True, capture_output=True)
            with self.assertRaisesRegex(ValueError, 'repository/scope mismatch'):
                repository_counter.allocate(other, {}, remote='unused')


if __name__ == '__main__':
    unittest.main()
