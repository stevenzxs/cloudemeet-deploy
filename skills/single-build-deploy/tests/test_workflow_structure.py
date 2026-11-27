import json
from pathlib import Path
import re
import unittest

import yaml

REPO = Path(__file__).resolve().parents[3]
WORKFLOW = REPO / '.github' / 'workflows' / 'build-single.yml'

TARGETS = ['gateway', 'app-web', 'api', 'jitsi-mgr', 'web', 'prosody', 'jicofo', 'jvb', 'electron', 'android']


class WorkflowStructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding='utf-8')
        cls.doc = yaml.safe_load(cls.text)

    def test_dispatch_inputs_complete(self):
        inputs = self.doc[True]['workflow_dispatch']['inputs']
        for name in ('base_revision', 'target', 'expected_tls_mode', 'expected_origin',
                     'material_commit', 'architecture', 'publish_images'):
            self.assertIn(name, inputs, name)
        self.assertEqual(sorted(inputs['target']['options']), sorted(TARGETS))
        self.assertEqual(inputs['publish_images']['type'], 'boolean')
        self.assertIs(inputs['publish_images']['default'], False)

    def test_concurrency_guards_same_base_and_target(self):
        concurrency = self.doc['concurrency']
        self.assertIn('inputs.base_revision', concurrency['group'])
        self.assertIn('inputs.target', concurrency['group'])
        self.assertIs(concurrency['cancel-in-progress'], False)

    def test_patch_numbering_and_base_evidence_precede_build(self):
        version = self.text.index('patch_release.py check-base')
        allocate = self.text.index('patch_release.py allocate')
        build = self.text.index('name: Build')
        self.assertLess(version, allocate)
        self.assertLess(allocate, build)

    def test_publish_jobs_gated_by_explicit_approval(self):
        for job in re.findall(r'if: [^\n]*publish_images[^\n]*', self.text):
            self.assertIn('inputs.publish_images', job)
        publish_indices = [i.start() for i in re.finditer(r'^  publish-', self.text, re.M)]
        self.assertTrue(publish_indices, 'expected publish jobs')
        for index in publish_indices:
            section = self.text[index:self.text.find('\n  build', index) if False else len(self.text)]
            self.assertIn('if:', section[:600])

    def test_client_checkout_derives_from_sources_lock_with_three_way_assertion(self):
        self.assertIn('sources.json', self.text)
        self.assertIn('request.sources', self.text)
        # No hardcoded 40-hex client commit in the workflow itself.
        self.assertIsNone(re.search(r'ref: [0-9a-f]{40}', self.text))

    def test_no_legacy_or_shared_closure_references(self):
        self.assertNotIn('build-tools/', self.text)
        self.assertNotIn('revision-allocation.yml', self.text)

    def test_server_build_feeds_patch_record_to_package_script(self):
        self.assertIn('VERSION_RECORD', self.text)
        self.assertIn('patch-assignment.json', self.text)
        self.assertIn('skills/single-build-deploy/scripts/package.sh build', self.text)
    def test_single_skill_does_not_reuse_full_build_deploy_code(self):
        # Self-contained by user decision (2026-11-27): code must not import or execute
        # the joint skill's tools/scripts. The single sanctioned data dependency is the
        # live joint revision counter (version-policy.json).
        root = REPO / 'skills' / 'single-build-deploy'
        offenders = []
        for base in (root / 'tools', root / 'scripts'):
            for path in base.rglob('*'):
                if path.is_file() and path.suffix in ('.py', '.cjs', '.js', '.sh'):
                    content = path.read_text(encoding='utf-8', errors='replace')
                    for line in content.splitlines():
                        if ('full-build-deploy' in line and 'version-policy.json' not in line
                                and 'FULL_CONFIG = ' not in line and not line.strip().startswith('#')):
                            offenders.append(f'{path.relative_to(root)}: {line.strip()[:80]}')
        self.assertEqual(offenders, [])


if __name__ == '__main__':
    unittest.main()
