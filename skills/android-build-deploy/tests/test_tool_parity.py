"""Drift guard: this skill's self-contained copies must stay byte-identical to the
full-build-deploy maintenance source. Change both sides together and rerun tests.
The only sanctioned cross-skill data dependency is the live joint revision counter
(version-policy.json), which is intentionally NOT copied.
"""
from pathlib import Path
import unittest

REPO = Path(__file__).resolve().parents[3]
SKILL = REPO / 'skills' / 'android-build-deploy'
SOURCE = REPO / 'skills' / 'full-build-deploy'

CONFIG_FILES = ['client.env', 'client-ca.crt', 'client-ca.json', 'signing-policy.json']


class ToolParityTests(unittest.TestCase):
    def test_config_copies_match_maintenance_source(self):
        for name in CONFIG_FILES:
            mine = (SKILL / 'config' / name).read_bytes()
            theirs = (SOURCE / 'config' / name).read_bytes()
            self.assertEqual(mine, theirs, f'config/{name} differs from full-build-deploy')

    def test_client_tool_copies_match_maintenance_source(self):
        mine_root = SKILL / 'tools' / 'clients'
        theirs_root = SOURCE / 'tools' / 'clients'
        mine = {p.relative_to(mine_root) for p in mine_root.rglob('*') if p.is_file()}
        theirs = {p.relative_to(theirs_root) for p in theirs_root.rglob('*') if p.is_file()}
        self.assertEqual(mine, theirs, 'file sets differ')
        for relative in sorted(mine):
            self.assertEqual((mine_root / relative).read_bytes(), (theirs_root / relative).read_bytes(),
                             f'tools/clients/{relative} differs from full-build-deploy')

    def test_version_counter_is_not_copied(self):
        self.assertFalse((SKILL / 'config' / 'version-policy.json').exists(),
                         'live joint revision counter must be read from full-build-deploy, never copied')


if __name__ == '__main__':
    unittest.main()
