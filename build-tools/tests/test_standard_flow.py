"""No network, no allocation, no deployment: standard-entry regression."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class StandardFlow(unittest.TestCase):
    def module(self):
        spec = importlib.util.spec_from_file_location('delivery_target', ROOT/'build-tools/delivery-target.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_origin_only_derives_target(self):
        value = self.module().derive('https://118.193.36.35:8443', ROOT)
        self.assertEqual(value['origin'], 'https://118.193.36.35:8443')
        self.assertEqual(value['target']['MEDIA_HOST'], '118.193.36.35')
        self.assertEqual(value['target']['HTTPS_PORT'], '8443')
        self.assertEqual(value['target']['MEDIA_PORT'], '10000')
        self.assertEqual(value['client']['CLIENT_VERSION'], '1.0.21')

    def test_domain_requires_unique_current_target_identity(self):
        m = self.module()
        with self.assertRaises(ValueError):
            m.derive('https://meet.example:8443', ROOT)
        result = m.derive('https://meet.example:8443', ROOT,
                          resolved=['118.193.36.35'], target_ipv4='118.193.36.35')
        self.assertEqual(result['target']['MEDIA_HOST'], '118.193.36.35')
        for ips, identity in [(['118.193.36.35','1.1.1.1'],'118.193.36.35'), (['1.1.1.1'],'118.193.36.35')]:
            with self.assertRaises(ValueError):
                m.derive('https://meet.example', ROOT, resolved=ips, target_ipv4=identity)

    def test_unsafe_origin_rejected(self):
        for origin in ['https://u:p@example.com', 'https://example.com/path', 'http://118.193.36.35',
                       'https://127.0.0.1', 'https://[::1]', 'https://example.com?x=1', 'https://118.193.36.35:0']:
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                self.module().derive(origin, ROOT)

    def test_installed_skill_contract_is_versioned(self):
        skill = (ROOT/'skills/cloudmeet-online-delivery/SKILL.md').read_text(encoding='utf-8')
        for term in ['setup.py', 'build-joint.yml', 'Windows', '签名', '不重复确认', '备份', '短提示词', 'JVB', 'main']:
            self.assertIn(term, skill)
        for obsolete in ['最小实施方案', '未签名产物，如实标注', '等用户按确认句式回复']:
            self.assertNotIn(obsolete, skill)


if __name__ == '__main__':
    unittest.main()
