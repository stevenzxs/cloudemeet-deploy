import json
from pathlib import Path
import re
import unittest

import yaml

REPO = Path(__file__).resolve().parents[3]
SKILL = REPO / 'skills' / 'server-build-deploy'
WORKFLOW = REPO / '.github' / 'workflows' / 'build-server.yml'

SERVICES = ['gateway', 'app-web', 'api', 'jitsi-mgr', 'web', 'prosody', 'jicofo', 'jvb']


class ServerWorkflowStructureTests(unittest.TestCase):
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
        for name in ('expected_tls_mode', 'expected_origin', 'material_commit', 'architecture', 'publish_images'):
            self.assertIn(name, inputs, name)
        self.assertEqual(sorted(inputs['expected_tls_mode']['options']), ['caddy-public-acme', 'private-ca'])
        self.assertEqual(inputs['expected_tls_mode']['default'], 'private-ca')
        self.assertEqual(sorted(inputs['architecture']['options']), ['amd64', 'arm64'])
        self.assertEqual(inputs['publish_images']['type'], 'boolean')
        self.assertIs(inputs['publish_images']['default'], False)

    def test_version_job_allocates_server_scope_and_propagates_approval(self):
        jobs = self.text.split('\njobs:\n')[1]
        self.assertRegex(jobs, r'version:\n    permissions:\n      contents: write\n    uses: \./\.github/workflows/revision-allocation\.yml')
        self.assertIn("scope: '[\"server\"]'", jobs)
        self.assertIn('expected_tls_mode: ${{ inputs.expected_tls_mode }}', jobs)
        self.assertIn('expected_origin: ${{ inputs.expected_origin }}', jobs)

    def test_build_matrix_covers_all_services(self):
        build = self.doc['jobs']['build']
        self.assertEqual(sorted(build['strategy']['matrix']['service']), sorted(SERVICES))
        self.assertIn('ubuntu-24.04-arm', self.text)
        self.assertIn('build-service.sh', self.text)

    def test_source_pins_derive_from_sources_lock(self):
        sources = json.loads((SKILL / 'sources.json').read_text(encoding='utf-8'))
        self.assertEqual(sorted(sources['services']), sorted(SERVICES))
        for entry in sources['services'].values():
            self.assertRegex(entry['commit'], r'^[0-9a-f]{40}$')
        self.assertIn(".services[\"${{ matrix.service }}\"]", self.text)
        self.assertIn('Assert checkout matches source lock', self.text)
        lifecycle = sources['lifecycle']
        self.assertEqual(lifecycle['repository'], 'https://github.com/jitsi/docker-jitsi-meet.git')
        self.assertIn(lifecycle['commit'], self.text)

    def test_publish_gated_and_sync_upload(self):
        self.assertIn('if: inputs.publish_images', self.text)
        publish = self.text[self.text.index('  publish:'):]
        self.assertIn('packages: write', publish)
        self.assertIn('ghcr.io/stevenzxs/cloudmeet-${service}', publish.replace('-${service}', '-${service}'))
        self.assertIn('GH_REPO', publish)
        self.assertIn('--draft', publish)
        self.assertIn('--latest=false', publish)
        self.assertIn('gh release upload', publish)
        self.assertNotIn('assets=$(gh release view', publish)
        self.assertIn('--draft=false', publish)
        self.assertIn('NOT_DEPLOYED', publish)
        self.assertLess(publish.index('gh release create'), publish.index('gh release upload'))
        self.assertLess(publish.index('gh release upload'), publish.index('gh release edit'))

    def test_publish_verifies_archive_digests_before_push(self):
        publish = self.text[self.text.index('  publish:'):]
        self.assertIn('Archive digest mismatch', publish)
        self.assertLess(publish.index('Archive digest mismatch'), publish.index('docker push'))

    def test_no_legacy_closure_references(self):
        self.assertNotIn('build-tools/', self.text)
        self.assertNotIn('skills/full-build-deploy/scripts/package.sh', self.text)

    def test_material_identity_check_expands_github_sha(self):
        # Run 45988672971: single-quoted '$GITHUB_SHA' compared literally and
        # always failed; the variable must be expanded (double quotes).
        self.assertNotIn("'$GITHUB_SHA'", self.text)
        self.assertIn('"$GITHUB_SHA"', self.text)

    def test_maven_builds_route_through_tencent_mirror(self):
        # Central 429-throttles CI runners (run 45989299222 api job).
        script = (SKILL / 'tools' / 'build-service.sh').read_text(encoding='utf-8')
        self.assertIn('mirrors.cloud.tencent.com', script)
        self.assertIn('mirrorOf>central<', script)

    def test_lifecycle_ref_is_literal_not_fromjson(self):
        # fromJSON('2768…') is parsed as a number and breaks the workflow template.
        self.assertIsNone(re.search(r"fromJSON\('[^']*[0-9a-f]{40}[^']*'\)", self.text))


if __name__ == '__main__':
    unittest.main()
