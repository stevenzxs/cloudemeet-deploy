import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

from tls_contract import validate


class DynamicOriginTests(unittest.TestCase):
    def base(self, mode="private-ca"):
        return {
            "SITE_DOMAIN": "stale-config.example",
            "SITE_SCHEME": "https",
            "SITE_PORT": "443",
            "TLS_MODE": mode,
            "CLIENT_CA_FILE": "client-ca.crt" if mode == "private-ca" else "",
        }

    def test_user_domain_origin_is_authoritative_over_fixed_origin(self):
        result = validate(self.base(), "private-ca", "https://cloudmeet.stevenzxs.cn")
        self.assertEqual(result["origin"], "https://cloudmeet.stevenzxs.cn")

    def test_user_ip_origin_is_allowed_for_private_ca(self):
        result = validate(self.base(), "private-ca", "https://118.193.36.35")
        self.assertEqual(result["origin"], "https://118.193.36.35")

    def test_public_acme_rejects_ip_and_non_default_port(self):
        config = self.base("caddy-public-acme")
        for origin in ("https://118.193.36.35", "https://cloudmeet.stevenzxs.cn:8443"):
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                validate(config, "caddy-public-acme", origin)

    def test_effective_origin_fields_are_returned_for_batch_config(self):
        result = validate(self.base(), "private-ca", "http://115.190.243.21:8080")
        self.assertEqual((result["scheme"], result["host"], result["port"]), ("http", "115.190.243.21", 8080))

    def test_tls_mode_is_an_approved_input_not_a_stale_client_env_constraint(self):
        config = self.base("caddy-public-acme")
        config["CLIENT_CA_FILE"] = ""
        result = validate(config, "private-ca", "https://meet.example.org")
        self.assertEqual(result['tls_mode'], "private-ca")
        self.assertEqual(result['client_ca_file'], 'client-ca.crt')


if __name__ == "__main__":
    unittest.main()
