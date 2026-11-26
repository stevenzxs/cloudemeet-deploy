from pathlib import Path
import unittest

SKILL_ROOT = Path(__file__).resolve().parents[1]
ROOT = SKILL_ROOT.parents[1]


class RevisionWorkflowTests(unittest.TestCase):
    def test_server_has_no_manual_version_or_push_fallback(self):
        text = (ROOT / '.github/workflows/build-package.yml').read_text(encoding='utf-8')
        self.assertNotIn('1.0.19-rc1', text)
        self.assertNotIn('  push:', text)
        self.assertIn('workflow_call:', text)
        self.assertIn('revision-allocation.yml', text)
        self.assertIn('VERSION_RECORD', text)

    def test_parent_workflow_allocates_once_and_children_inherit_assignment(self):
        joint = (ROOT / '.github/workflows/build-joint.yml').read_text(encoding='utf-8')
        self.assertEqual(joint.count('revision-allocation.yml'), 1)
        self.assertEqual(joint.count('assignment: ${{ needs.version.outputs.assignment }}'), 3)
        self.assertIn('needs: [version, server, clients]', joint)

    def test_allocator_uses_repository_policy_counter(self):
        text = (ROOT / '.github/workflows/revision-allocation.yml').read_text(encoding='utf-8')
        self.assertIn('runs-on: ubuntu-24.04', text)
        self.assertIn('contents: write', text)
        self.assertIn('Allocate revision in version policy on main', text)
        self.assertIn('GH_TOKEN', text)
        self.assertNotIn('CLOUDMEET_LEDGER_ANCHOR', text)
        self.assertNotIn('cloudmeet-revision-ledger', text)
        self.assertNotIn('self-hosted', text)

    def test_product_jobs_explicitly_keep_read_permissions(self):
        import re
        for filename, jobs in [('build-package.yml', ['build', 'package']), ('build-clients.yml', ['package'])]:
            text = (ROOT / '.github/workflows' / filename).read_text(encoding='utf-8')
            for name in jobs:
                body = re.split(r'\n  [a-z][a-z_-]*:\n', text.split('\n  ' + name + ':\n', 1)[1], maxsplit=1)[0]
                self.assertIn('    permissions:\n      contents: read', body)


if __name__ == '__main__':
    unittest.main()
