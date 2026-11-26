import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ConfigAllowlistTests(unittest.TestCase):
    def test_skill_config_contains_only_build_publish_inputs(self):
        allowed = {
            "client.env",
            "client-ca.crt",
            "client-ca.json",
            "h5-source.json",
            "signing-policy.json",
            "version-policy.json",
            "target.py",
        }
        actual = {path.name for path in (ROOT / "config").iterdir() if path.is_file()}
        self.assertEqual(actual, allowed)

    def test_private_and_deployment_material_is_not_in_skill_copy(self):
        forbidden = {"target.env", "jitsi.env", "jitsi-mgr.env", "jitsi-base.yaml", "docker-compose.yml", "start.sh", "init.py"}
        actual = {path.name for path in (ROOT / "config").iterdir()}
        self.assertTrue(forbidden.isdisjoint(actual))


if __name__ == "__main__":
    unittest.main()
