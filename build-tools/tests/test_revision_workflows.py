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
        self.assertEqual(text.count('assignment: ${{ needs.version.outputs.assignment }}'), 2)

    def test_allocator_is_persistent_and_not_an_artifact_counter(self):
        text = (ROOT / '.github/workflows/revision-allocation.yml').read_text()
        self.assertIn('cloudmeet-version-controller', text)
        self.assertIn('CLOUDMEET_VERSION_LEDGER', text)
        self.assertNotIn('initialize', text)
        self.assertNotIn('contents: write', text)

    def test_controller_joint_inheritance_retry_and_scope_binding(self):
        import revision_ledger
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
            (root / 'build-tools/sources.json').write_bytes((ROOT / 'build-tools/sources.json').read_bytes())
            ledger = Path(tmp) / 'persistent.sqlite'
            revision_ledger.initialize(ledger, policy)
            output = Path(tmp) / 'output'
            env = dict(GITHUB_SHA='a' * 40, MATERIAL_SHA='a' * 40, GITHUB_RUN_ID='100',
                       GITHUB_RUN_ATTEMPT='1', GITHUB_REPOSITORY='stevenzxs/cloudemeet-deploy',
                       GITHUB_EVENT_NAME='workflow_dispatch', GITHUB_REF='refs/heads/main',
                       GITHUB_WORKFLOW_REF='stevenzxs/cloudemeet-deploy/.github/workflows/build-joint.yml@refs/heads/main',
                       VERSION_LEDGER=str(ledger), GITHUB_OUTPUT=str(output),
                       REQUEST_SCOPE='["server","electron","android"]', INHERITED_ASSIGNMENT='')
            previous = Path.cwd()
            try:
                os.chdir(root)
                with patch.dict(os.environ, env, clear=True), patch.object(controller.subprocess, 'check_output', return_value='a' * 40):
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
