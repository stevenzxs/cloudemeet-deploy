from pathlib import Path
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'build-tools'))


class RevisionWorkflowTests(unittest.TestCase):
    def test_server_has_no_manual_version_or_push_fallback(self):
        text = (ROOT / '.github/workflows/build-package.yml').read_text()
        self.assertNotIn('1.0.19-rc1', text)
        self.assertNotIn('  push:', text)
        self.assertIn('workflow_call:', text)
        self.assertIn('revision-allocation.yml', text)
        self.assertIn('VERSION_RECORD', text)

    def test_joint_has_single_parent_assignment(self):
        text = (ROOT / '.github/workflows/build-joint.yml').read_text()
        self.assertEqual(text.count('revision-allocation.yml'), 1)
        self.assertEqual(text.count('assignment: ${{ needs.version.outputs.assignment }}'), 3)
        self.assertIn('needs: [version, server, clients]', text)

    def test_allocator_is_persistent_and_not_an_artifact_counter(self):
        text = (ROOT / '.github/workflows/revision-allocation.yml').read_text()
        self.assertIn('runs-on: ubuntu-24.04', text)
        self.assertIn('CLOUDMEET_LEDGER_ANCHOR', text)
        self.assertIn('contents: write', text)
        self.assertNotIn('self-hosted', text)
        self.assertNotIn('initialize', text)

    def test_auth_header_shell_produces_basic_credentials(self):
        import base64
        import subprocess
        text = (ROOT / '.github/workflows/revision-allocation.yml').read_text()
        script = '\n'.join(line[10:] for line in text.split('        run: |\n', 1)[1].split('          python3 -B', 1)[0].splitlines())
        result = subprocess.run(['bash', '-e', '-c', script + '\nprintf "%s" "$LEDGER_AUTH_HEADER"'],
                                env=dict(os.environ, GH_TOKEN='fixture-not-a-secret'), capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        expected = 'AUTHORIZATION: basic ' + base64.b64encode(b'x-access-token:fixture-not-a-secret').decode()
        self.assertEqual(result.stdout.splitlines()[-1], expected)

    def test_product_jobs_explicitly_keep_read_permissions(self):
        import re
        for filename, jobs in [('build-package.yml', ['build', 'package']), ('build-clients.yml', ['package'])]:
            text = (ROOT / '.github/workflows' / filename).read_text()
            for name in jobs:
                body = re.split(r'\n  [a-z][a-z_-]*:\n', text.split('\n  ' + name + ':\n', 1)[1], maxsplit=1)[0]
                self.assertIn('    permissions:\n      contents: read', body)

    def test_controller_joint_inheritance_retry_and_scope_binding(self):
        import revision_git_ledger
        import subprocess as sp
        spec = importlib.util.spec_from_file_location('controller', ROOT / 'build-tools/allocate-workflow.py')
        controller = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(controller)
        policy = dict(schema=1, namespace='cloudmeet-fixture', server_baseline='11248.0.2',
                      client_baseline='1.0.21', android_base_code=1021, previous_android_code=1021,
                      previous_msi_version='1.0.21', approved=True)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'repo'
            (root / 'config').mkdir(parents=True)
            (root / 'build-tools').mkdir()
            (root / 'config/version-policy.json').write_text(json.dumps(policy))
            (root / 'config/h5-source.json').write_text(json.dumps({'commit':'f'*40}))
            (root / 'build-tools/sources.json').write_bytes((ROOT / 'build-tools/sources.json').read_bytes())
            # Bootstrap a synthetic migrated fixture on a local bare remote, never live state.
            import revision_ledger
            ledger = Path(tmp) / 'fixture.sqlite'
            revision_ledger.initialize(ledger, policy)
            initial_request = dict(repository='stevenzxs/cloudemeet-deploy', workflow='fixture', run_id='99',
                                   configuration_sha='b'*40, task='fixture', scope=['server'], sources={'web':'c'*40})
            revision_ledger.allocate(ledger, policy, initial_request)
            remote = Path(tmp) / 'remote.git'
            seed = Path(tmp) / 'seed'
            sp.run(['git', 'init', '--bare', str(remote)], check=True, capture_output=True)
            sp.run(['git', 'init', str(seed)], check=True, capture_output=True)
            def git(*args):
                return sp.check_output(['git', '-C', str(seed), *args], text=True).strip()
            git('config', 'user.name', 'Test')
            git('config', 'user.email', 'test@example.invalid')
            git('checkout', '--orphan', 'cloudmeet-revision-ledger')
            (seed / 'ledger.json').write_text(json.dumps(revision_git_ledger.export_sqlite(ledger, policy)))
            git('add', 'ledger.json')
            git('commit', '-m', 'fixture')
            git('push', str(remote), 'HEAD:refs/heads/cloudmeet-revision-ledger')
            anchor = git('rev-parse', 'HEAD')
            output = Path(tmp) / 'output'
            env = dict(GITHUB_SHA='a' * 40, MATERIAL_SHA='a' * 40, GITHUB_RUN_ID='100',
                       GITHUB_RUN_ATTEMPT='1', GITHUB_REPOSITORY='stevenzxs/cloudemeet-deploy',
                       GITHUB_EVENT_NAME='workflow_dispatch', GITHUB_REF='refs/heads/main',
                       GITHUB_WORKFLOW_REF='stevenzxs/cloudemeet-deploy/.github/workflows/build-joint.yml@refs/heads/main',
                       LEDGER_REMOTE=str(remote), LEDGER_ANCHOR=anchor, GITHUB_OUTPUT=str(output),
                       REQUEST_SCOPE='["server","electron","android"]', INHERITED_ASSIGNMENT='')
            previous = Path.cwd()
            try:
                os.chdir(root)
                with patch.dict(os.environ, env, clear=True), patch.object(controller, 'configuration_sha', return_value='a' * 40):
                    controller.main()
                    first = json.loads(output.read_text().split('assignment=', 1)[1])
                    os.environ['GITHUB_RUN_ATTEMPT'] = '2'
                    controller.main()
                    os.environ['REQUEST_SCOPE'] = '["server"]'
                    os.environ['INHERITED_ASSIGNMENT'] = json.dumps(first)
                    controller.main()
                    records = [json.loads(line.split('=', 1)[1]) for line in output.read_text().splitlines()]
                    self.assertEqual(records, [first, first, first])
                    os.environ['GITHUB_REF'] = 'refs/heads/unreviewed'
                    with self.assertRaises(ValueError):
                        controller.main()
            finally:
                os.chdir(previous)


if __name__ == '__main__':
    unittest.main()
