from pathlib import Path
import re
import unittest


SKILL_DIR = Path(__file__).resolve().parents[1]


class SkillBoundaryTests(unittest.TestCase):
    def test_skill_declares_name_and_exact_eight_services(self):
        skill = (SKILL_DIR / 'SKILL.md').read_text(encoding='utf-8')
        self.assertIn('name: cloudmeet-first-install', skill)
        services = ('web', 'app-web', 'api', 'jitsi-mgr', 'gateway',
                    'prosody', 'jicofo', 'jvb')
        self.assertTrue(all(f'`{service}`' in skill for service in services))

    def test_skill_is_first_install_only_and_has_explicit_boundaries(self):
        skill = (SKILL_DIR / 'SKILL.md').read_text(encoding='utf-8').lower()
        self.assertIn('first-time', skill)
        self.assertIn('authorization', skill)
        self.assertIn('stop and report', skill)
        self.assertIn('does not authorize', skill)

    def test_skill_has_no_dependency_on_other_skill_directories(self):
        skill = (SKILL_DIR / 'SKILL.md').read_text(encoding='utf-8')
        self.assertIsNone(re.search(r'(?:\.\./)+skills/|skills/(?!first-install/)[\w-]+/', skill))

    def test_skill_excludes_build_release_client_upgrade_and_offline_flows(self):
        skill = (SKILL_DIR / 'SKILL.md').read_text(encoding='utf-8').lower()
        self.assertIn('does not cover builds, releases, clients, upgrades, or offline installation', skill)
        self.assertNotRegex(skill, r'(?:skills/[^\s]+/tools/|python\s+[^\n]*(?:deploy|install)\.py)')


if __name__ == '__main__':
    unittest.main()
