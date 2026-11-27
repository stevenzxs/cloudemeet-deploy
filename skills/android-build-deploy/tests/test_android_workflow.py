import json
from pathlib import Path
import re
import unittest

import yaml

REPO = Path(__file__).resolve().parents[3]
SKILL = REPO / 'skills' / 'android-build-deploy'
WORKFLOW = REPO / '.github' / 'workflows' / 'build-android.yml'


class AndroidWorkflowStructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding='utf-8')
        cls.doc = yaml.safe_load(cls.text)

    def test_dispatch_only_inputs_complete(self):
        triggers = self.doc[True]
        self.assertIn('workflow_dispatch', triggers)
        self.assertNotIn('pull_request', triggers)
        self.assertNotIn('push', triggers)
        inputs = triggers['workflow_dispatch']['inputs']
        for name in ('expected_tls_mode', 'expected_origin', 'material_commit', 'publish_images'):
            self.assertIn(name, inputs, name)
        self.assertEqual(sorted(inputs['expected_tls_mode']['options']), ['caddy-public-acme', 'private-ca'])
        self.assertEqual(inputs['expected_tls_mode']['default'], 'private-ca')
        self.assertEqual(inputs['publish_images']['type'], 'boolean')
        self.assertIs(inputs['publish_images']['default'], False)

    def test_version_job_allocates_android_scope_and_propagates_approval(self):
        jobs = self.text.split('\njobs:\n')[1]
        self.assertRegex(jobs, r'version:\n    permissions:\n      contents: write\n    uses: \./\.github/workflows/revision-allocation\.yml')
        self.assertIn("scope: '[\"android\"]'", jobs)
        self.assertIn('expected_tls_mode: ${{ inputs.expected_tls_mode }}', jobs)
        self.assertIn('expected_origin: ${{ inputs.expected_origin }}', jobs)

    def test_build_pins_source_lock_and_skill_owned_builder(self):
        sources = json.loads((SKILL / 'sources.json').read_text(encoding='utf-8'))
        commit = sources['clients']['android']['commit']
        self.assertRegex(commit, r'^[0-9a-f]{40}$')
        self.assertIn(f'ref: {commit}', self.text)
        self.assertIn('repository: stevenzxs/jm', self.text)
        self.assertIn('deploy/skills/android-build-deploy/tools/clients/build-clients.cjs --target android', self.text)
        self.assertIn('--version-record version-assignment.json', self.text)

    def test_signing_required_and_no_windows_credentials(self):
        self.assertIn('ANDROID_KEYSTORE_BASE64', self.text)
        self.assertIn('debug fallback prohibited', self.text)
        for key in ('WINDOWS_PFX_BASE64', 'WINDOWS_PFX_PASSWORD', 'CERTIFICATES_READ_TOKEN', 'SIGNTOOL_PATH'):
            self.assertNotIn(key, self.text)

    def test_publish_gated_and_immutable(self):
        self.assertRegex(self.text, re.compile(r'if: inputs\.publish_images'))
        publish = self.text[self.text.index('  publish:'):]
        self.assertIn('sha256sum -c SHA256SUMS', publish)
        self.assertIn('build-evidence.json', publish)
        self.assertIn('--draft', publish)
        self.assertIn('--latest=false', publish)
        self.assertIn('--draft=false', publish)
        self.assertIn('NOT_DEPLOYED', publish)
        self.assertIn('GH_REPO', publish, 'publish job runs without checkout; gh needs GH_REPO to resolve the repository')
        self.assertIn('cloudmeet-android-r${REVISION}-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}', publish)
        # draft create precedes final publish
        self.assertLess(publish.index('gh release create'), publish.index('gh release edit'))

    def test_no_legacy_closure_references(self):
        self.assertNotIn('build-tools/', self.text)
        self.assertNotIn('pull_request:', self.text)


if __name__ == '__main__':
    unittest.main()
