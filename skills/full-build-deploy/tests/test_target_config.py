import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('target_config', ROOT/'config/target.py')
target = importlib.util.module_from_spec(spec)
spec.loader.exec_module(target)


class TargetTests(unittest.TestCase):
    def test_runtime_target_resolution_applies_packaged_origin_contract(self):
        import json
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'target.env').write_text('SITE_SCHEME=https\nHTTPS_PORT=9443\nHTTP_PORT=8080\nMEDIA_PORT=10000\nMEDIA_HOST=\n',encoding='utf-8')
            provenance=root/'provenance';provenance.mkdir()
            contract={'origin':'https://meet.example:8443','scheme':'https','host':'meet.example','port':8443,'addresses':['203.0.113.8']}
            (provenance/'origin-contract.json').write_text(json.dumps(contract),encoding='utf-8')
            values=target.resolve_target(root)
            self.assertEqual(values['PUBLIC_URL'],contract['origin'])
            self.assertEqual(values['SITE_HOST'],'meet.example')
            self.assertEqual(values['HTTPS_PORT'],'8443')

    def test_apply_origin_contract_updates_public_server_entry_without_replacing_dns_with_ip(self):
        contract = {'origin':'https://meet.example:8443','scheme':'https','host':'meet.example',
                    'port':8443,'addresses':['203.0.113.8']}
        values = target.apply_origin_contract(target.validate_target({
            'SITE_SCHEME':'https','HTTPS_PORT':'8443','HTTP_PORT':'8080','MEDIA_PORT':'10000','MEDIA_HOST':''
        }), contract)
        self.assertEqual(values['PUBLIC_URL'], 'https://meet.example:8443')
        self.assertEqual(values['SITE_HOST'], 'meet.example')
        self.assertEqual(values['HTTPS_PORT'], '8443')
        self.assertNotEqual(values['PUBLIC_URL'], 'https://203.0.113.8:8443')

    def test_apply_origin_contract_rejects_port_mismatch_and_invalid_contract(self):
        values = target.validate_target({'SITE_SCHEME':'https','HTTPS_PORT':'8443','HTTP_PORT':'8080','MEDIA_PORT':'10000','MEDIA_HOST':''})
        for contract in [
                {'origin':'https://meet.example:8443','scheme':'https','host':'meet.example','port':443,'addresses':['203.0.113.8']},
                {'origin':'https://meet.example:8443','scheme':'https','host':'other.example','port':8443,'addresses':['203.0.113.8']},
                {'origin':'https://meet.example:8443','scheme':'https','host':'meet.example','port':8443,'addresses':[]},
        ]:
            with self.subTest(contract=contract), self.assertRaises(ValueError):
                target.apply_origin_contract(values, contract)

    def test_origin_override_preserves_existing_customization(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'custom-config.js'
            target.install_origin_config(path)
            self.assertIn('window.location.host', path.read_text())
            self.assertNotIn('cloudmeet.internal', path.read_text())
            target.install_origin_config(path)
            path.write_text('// user customization')
            with self.assertRaises(ValueError):
                target.install_origin_config(path)
            self.assertEqual(path.read_text(), '// user customization')

    def test_gateway_has_no_fixed_ip_host_filter_or_redirect(self):
        text = (Path(__file__).resolve().parents[3]/'config/Caddyfile').read_text(encoding='utf-8')
        self.assertIn('https://:443', text)
        self.assertIn('fallback_sni cloudmeet.internal', text)
        self.assertNotIn('{$SITE_HOST}', text)
        self.assertNotIn('redir ', text)

    def test_derives_one_host_and_ports(self):
        values = target.validate_target({'SITE_SCHEME':'https','HTTPS_PORT':'8443','HTTP_PORT':'8080','MEDIA_PORT':'10000','MEDIA_HOST':''})
        self.assertNotIn('SERVER_HOST', values)
        self.assertEqual(values['JVB_ADVERTISE_IPS'], '')
        self.assertEqual(values['SITE_HOST'], 'cloudmeet.internal')

    def test_rejects_invalid_or_duplicate_values(self):
        base = {'SITE_SCHEME':'https','HTTPS_PORT':'8443','HTTP_PORT':'8080','MEDIA_PORT':'10000','MEDIA_HOST':''}
        for broken in (dict(base, SERVER_HOST='1.2.3.4'), dict(base, PUBLIC_URL='https://old'),
                       dict(base, HTTPS_PORT='8080'), dict(base, HTTPS_PORT='65536'),
                       dict(base, SITE_SCHEME='http')):
            with self.subTest(broken=broken), self.assertRaises(ValueError):
                target.validate_target(broken)

    def test_other_target_changes_all_derived_addresses(self):
        values = target.validate_target({'SITE_SCHEME':'https','HTTPS_PORT':'9443','HTTP_PORT':'8080','MEDIA_PORT':'10000','MEDIA_HOST':'192.0.2.8'})
        self.assertEqual(values['PUBLIC_URL'], 'https://cloudmeet.internal')
        self.assertEqual(values['SITE_HOST'], 'cloudmeet.internal')
        self.assertEqual(values['JVB_ADVERTISE_IPS'], '192.0.2.8')
