"""No Docker, ACME orders or target changes: dual TLS policy regression."""
import importlib.util
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('tls_certificate',ROOT/'build-tools/offline-runtime/certificate.py')
cert=importlib.util.module_from_spec(spec);spec.loader.exec_module(cert)


class DualTLS(unittest.TestCase):
    def test_explicit_public_policy(self):
        manifest={'tls_mode':'caddy-public-acme','client_origin':'https://meet.example.com','client_ca_sha256':None}
        self.assertEqual(cert.require_mode(manifest,'https://meet.example.com'),'caddy-public-acme')
        for origin in ['https://127.0.0.1','https://meet.example.com:8443','http://meet.example.com']:
            with self.assertRaises(ValueError):cert.require_mode(manifest,origin)
        with self.assertRaises(ValueError):cert.require_mode(dict(manifest,client_ca_sha256='a'*64),manifest['client_origin'])
        with self.assertRaises(ValueError):cert.require_mode({'tls_mode':'unknown'},manifest['client_origin'])

    def test_public_template_preserves_internal_routes_and_has_no_private_fallback(self):
        original=(ROOT/'config/Caddyfile').read_text()
        result=cert.public_caddy(original,'https://meet.example.com')
        self.assertIn('https://meet.example.com {',result)
        self.assertIn('disable_http_challenge',result)
        self.assertIn('https://gateway:9443',result)
        self.assertNotIn('tls internal',result)
        self.assertNotIn('https://:443',result)
        self.assertIn('import meeting_routes',result)
        with self.assertRaises(ValueError):cert.public_caddy('unexpected','https://meet.example.com')

    def test_legacy_private_policy(self):
        self.assertEqual(cert.require_mode({},'https://118.193.36.35:8443'),'private-ca')


if __name__=='__main__':unittest.main()
