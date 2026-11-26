import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

from origin_contract import normalize_origin


class OriginContractTests(unittest.TestCase):
    def test_https_uses_default_port_and_keeps_hostname(self):
        result = normalize_origin("https://cloudmeet.example", resolver=lambda host, port: ["203.0.113.8"])
        self.assertEqual(result["origin"], "https://cloudmeet.example")
        self.assertEqual(result["port"], 443)
        self.assertEqual(result["addresses"], ["203.0.113.8"])

    def test_http_uses_default_port(self):
        result = normalize_origin("http://cloudmeet.example", resolver=lambda host, port: ["203.0.113.9"])
        self.assertEqual(result["origin"], "http://cloudmeet.example")
        self.assertEqual(result["port"], 80)

    def test_explicit_port_is_preserved(self):
        result = normalize_origin("https://cloudmeet.example:8443", resolver=lambda host, port: ["203.0.113.10"])
        self.assertEqual(result["origin"], "https://cloudmeet.example:8443")
        self.assertEqual(result["port"], 8443)

    def test_multiple_addresses_are_sorted_and_unique(self):
        result = normalize_origin("https://cloudmeet.example", resolver=lambda host, port: ["2001:db8::2", "203.0.113.4", "203.0.113.4"])
        self.assertEqual(result["addresses"], ["203.0.113.4", "2001:db8::2"])

    def test_ipv4_literal_is_retained_as_origin_and_evidence(self):
        result = normalize_origin("https://118.193.36.35", resolver=lambda host, port: self.fail("literal must not resolve"))
        self.assertEqual(result["origin"], "https://118.193.36.35")
        self.assertEqual(result["addresses"], ["118.193.36.35"])

    def test_ipv6_literal_has_bracketed_authority_and_compressed_evidence(self):
        result = normalize_origin("https://[2001:0db8::1]:8443", resolver=lambda host, port: self.fail("literal must not resolve"))
        self.assertEqual(result["origin"], "https://[2001:db8::1]:8443")
        self.assertEqual(result["host"], "2001:db8::1")
        self.assertEqual(result["addresses"], ["2001:db8::1"])

    def test_rejects_path_credentials_and_missing_scheme(self):
        values = (
            "cloudmeet.example",
            "https://user:pass@cloudmeet.example",
            "https://cloudmeet.example/path",
            "https://cloudmeet.example/?q=1",
        )
        for value in values:
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_origin(value, resolver=lambda host, port: ["203.0.113.1"])

    def test_dns_failure_is_an_error(self):
        with self.assertRaises(ValueError):
            normalize_origin("https://cloudmeet.example", resolver=lambda host, port: [])

    def test_cli_writes_origin_contract_json(self):
        tools = Path(__file__).resolve().parents[1] / "tools"
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "origin-contract.json"
            env = dict(os.environ, EXPECTED_ORIGIN="https://cloudmeet.stevenzxs.cn:443", EXPECTED_TLS_MODE="caddy-public-acme")
            result = subprocess.run(
                [sys.executable, "-B", str(tools / "origin_contract.py"), "--output", str(output)],
                env=env, capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            contract = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(contract["origin"], "https://cloudmeet.stevenzxs.cn:443")


if __name__ == "__main__":
    unittest.main()
