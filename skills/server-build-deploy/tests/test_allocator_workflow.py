import unittest
import json
from pathlib import Path
import sys

import yaml


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'skills/server-build-deploy/tools/versioning'))
import allocate_workflow
from revision_versions import digest


class ServerAllocatorWorkflowTests(unittest.TestCase):
    def test_allocation_request_includes_required_server_source_pin(self):
        sources = {'services': {'gateway': {'commit': 'a' * 40},
                                'api': {'commit': 'b' * 40}},
                   'lifecycle': {'commit': 'c' * 40}}
        pins = allocate_workflow.source_identities(sources)
        server_inputs = {key: value for key, value in pins.items() if key != 'server'}
        self.assertEqual(pins['server'], digest(server_inputs))
        self.assertEqual(pins['lifecycle'], 'c' * 40)
        self.assertEqual(pins['gateway'], 'a' * 40)
        self.assertEqual(pins['api'], 'b' * 40)

    def test_server_workflow_uses_only_server_allocator_and_tools(self):
        workflow = yaml.safe_load((ROOT / '.github/workflows/allocate-server-revision.yml').read_text(encoding='utf-8'))
        text = (ROOT / '.github/workflows/allocate-server-revision.yml').read_text(encoding='utf-8')
        self.assertIn('skills/server-build-deploy/tools/versioning/allocate_workflow.py', text)
        self.assertIn('skills/server-build-deploy/config/version-policy.json', '\n'.join(
            path.read_text(encoding='utf-8') for path in (ROOT / 'skills/server-build-deploy/tools/versioning').glob('*.py')))
        self.assertNotIn('full-build-deploy', text)
        self.assertNotIn('revision-allocation.yml', text)
        self.assertIn("test \"$REQUEST_SCOPE\" = '[\"server\"]'", text)
        self.assertIn('ATTEMPT: ${{ github.run_attempt }}', text)
        self.assertIn('contents: write', text)
        self.assertIn('workflow_call', workflow[True])
        for name in ('origin_contract.py', 'tls_contract.py'):
            self.assertTrue((ROOT / 'skills/server-build-deploy/tools' / name).is_file())

    def test_standalone_server_workflow_routes_to_matching_allocator(self):
        text = (ROOT / '.github/workflows/build-server.yml').read_text(encoding='utf-8')
        self.assertIn('uses: ./.github/workflows/allocate-server-revision.yml', text)
        self.assertNotIn('revision-allocation.yml', text)
