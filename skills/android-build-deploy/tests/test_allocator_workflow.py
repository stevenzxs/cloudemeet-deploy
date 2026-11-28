import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[3]


class AndroidAllocatorWorkflowTests(unittest.TestCase):
    def test_android_workflow_uses_only_android_allocator_and_tools(self):
        workflow = yaml.safe_load((ROOT / '.github/workflows/allocate-android-revision.yml').read_text(encoding='utf-8'))
        text = (ROOT / '.github/workflows/allocate-android-revision.yml').read_text(encoding='utf-8')
        self.assertIn('skills/android-build-deploy/tools/versioning/allocate_workflow.py', text)
        self.assertIn('skills/android-build-deploy/config/version-policy.json', '\n'.join(
            path.read_text(encoding='utf-8') for path in (ROOT / 'skills/android-build-deploy/tools/versioning').glob('*.py')))
        self.assertNotIn('full-build-deploy', text)
        self.assertNotIn('revision-allocation.yml', text)
        self.assertIn('REQUEST_SCOPE', text)
        self.assertIn("test \"$REQUEST_SCOPE\" = '[\"android\"]'", text)
        self.assertIn('ATTEMPT: ${{ github.run_attempt }}', text)
        self.assertIn('contents: write', text)
        self.assertIn('workflow_call', workflow[True])
        for name in ('origin_contract.py', 'tls_contract.py'):
            self.assertTrue((ROOT / 'skills/android-build-deploy/tools' / name).is_file())

    def test_standalone_android_workflow_routes_to_matching_allocator(self):
        text = (ROOT / '.github/workflows/build-android.yml').read_text(encoding='utf-8')
        self.assertIn('uses: ./.github/workflows/allocate-android-revision.yml', text)
        self.assertNotIn('revision-allocation.yml', text)
