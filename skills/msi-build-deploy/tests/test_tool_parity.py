"""Ownership checks for MSI-maintained client tooling."""
from pathlib import Path
import unittest

SKILL = Path(__file__).resolve().parents[1]


class MsiToolOwnershipTests(unittest.TestCase):
    def test_msi_tools_and_policy_are_skill_owned(self):
        for name in ('build-clients.cjs', 'revision-config.cjs'):
            self.assertTrue((SKILL / 'tools/clients' / name).is_file())
        self.assertTrue((SKILL / 'config/version-policy.json').is_file())
        self.assertNotIn('full-build-deploy', (SKILL / 'tools/versioning/repository_counter.py').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
