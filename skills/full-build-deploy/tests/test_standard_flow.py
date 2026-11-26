"""No network, no allocation, no deployment: standard-entry regression."""
import importlib.util
from pathlib import Path
import unittest

REPO = Path(__file__).resolve().parents[3]
ROOT = REPO/'skills/full-build-deploy'


class StandardFlow(unittest.TestCase):
    def module(self):
        spec = importlib.util.spec_from_file_location('delivery_target', ROOT/'tools/delivery-target.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_origin_only_derives_target(self):
        value = self.module().derive('https://118.193.36.35:8443', REPO)
        self.assertEqual(value['origin'], 'https://118.193.36.35:8443')
        self.assertEqual(value['target']['MEDIA_HOST'], '118.193.36.35')
        self.assertEqual(value['target']['HTTPS_PORT'], '8443')
        self.assertEqual(value['target']['MEDIA_PORT'], '10000')
        self.assertEqual(value['client']['CLIENT_VERSION'], '1.0.21')

    def test_domain_requires_unique_current_target_identity(self):
        m = self.module()
        with self.assertRaises(ValueError):
            m.derive('https://meet.example:8443', REPO)
        result = m.derive('https://meet.example:8443', REPO,
                          resolved=['118.193.36.35'], target_ipv4='118.193.36.35')
        self.assertEqual(result['target']['MEDIA_HOST'], '118.193.36.35')
        for ips, identity in [(['118.193.36.35','1.1.1.1'],'118.193.36.35'), (['1.1.1.1'],'118.193.36.35')]:
            with self.assertRaises(ValueError):
                m.derive('https://meet.example', REPO, resolved=ips, target_ipv4=identity)

    def test_unsafe_origin_rejected(self):
        for origin in ['https://u:p@example.com', 'https://example.com/path', 'http://118.193.36.35',
                       'https://127.0.0.1', 'https://[::1]', 'https://example.com?x=1', 'https://118.193.36.35:0']:
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                self.module().derive(origin, REPO)

    def test_installed_skill_contract_is_versioned(self):
        skill = (REPO/'skills/cloudmeet-online-delivery/SKILL.md').read_text(encoding='utf-8')
        self.assertIn('name: cloudmeet-online-delivery', skill)

    def test_skill_records_observed_cron_failure_boundaries(self):
        skill = (REPO/'skills/cloudmeet-online-delivery/SKILL.md').read_text(encoding='utf-8')
        self.assertIn('## 双证书模式操作', skill)


if __name__ == '__main__':
    unittest.main()
