import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    'arm64', Path(__file__).resolve().parents[1] / 'tools/arm64-integration.py')


class IntegrationGateTests(unittest.TestCase):
    def test_prosody_storage_parent_is_owned_by_runtime_user(self):
        dockerfile = (Path(__file__).resolve().parents[1] /
                      'tools/arm64-prosody-core.Dockerfile').read_text()
        self.assertIn('install -d -o 1000 -g 1000 /var/lib/prosody /var/lib/prosody/data', dockerfile)

    def test_gate_requires_one_bridge_and_all_stable_containers(self):
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        good = [{'running': True, 'oom': False, 'restarts': 0}] * 3
        self.assertTrue(module.accepts({'bridge_selector': {'operational_bridge_count': 1}}, good))
        self.assertFalse(module.accepts({'bridge_selector': {'operational_bridge_count': 0}}, good))
        self.assertFalse(module.accepts({}, good))
        self.assertFalse(module.accepts({'bridge_selector': {'operational_bridge_count': 1}}, good[:2]))
        bad = good[:2] + [{'running': True, 'oom': False, 'restarts': 1}]
        self.assertFalse(module.accepts({'bridge_selector': {'operational_bridge_count': 1}}, bad))


if __name__ == '__main__':
    unittest.main()
