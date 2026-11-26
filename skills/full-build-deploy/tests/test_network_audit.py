import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

TOOLS = Path(__file__).resolve().parents[1] / 'tools'


class NetworkAuditTests(unittest.TestCase):
    def audit(self, **kwargs):
        spec = importlib.util.spec_from_file_location('network_audit', TOOLS/'network-audit.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.audit(**kwargs)

    def test_generic_explicitly_defers_empty_media(self):
        report = self.audit(root=TOOLS.parents[2], mode='generic')
        self.assertEqual(report['errors'], [])
        self.assertTrue(any(r['name'] == 'MEDIA_HOST' and r['status'] == 'deferred'
                            for r in report['parameters']))
        self.assertTrue(all(s in report['services'] for s in ['gateway', 'app-web', 'api', 'web', 'prosody', 'jicofo', 'jvb']))

    def test_target_rejects_empty_and_loopback_media(self):
        for host in ['', '127.0.0.1', '0.0.0.0', '224.0.0.1']:
            with self.subTest(host=host):
                r = self.audit(root=TOOLS.parents[2], mode='target', target={'MEDIA_HOST': host})
                self.assertTrue(r['errors'])

    def test_target_allows_lan_media_and_rejects_bad_port(self):
        self.assertEqual(self.audit(root=TOOLS.parents[2], mode='target',
                                   target={'MEDIA_HOST': '10.1.2.28'})['errors'], [])
        self.assertTrue(self.audit(root=TOOLS.parents[2], mode='generic',
                                  target={'MEDIA_PORT': '70000'})['errors'])

    def test_rendered_media_and_internal_port_exposure(self):
        services = {s: {} for s in ['gateway', 'app-web', 'api', 'web', 'prosody', 'jicofo', 'jvb']}
        services['jvb'] = {'environment': {'JVB_ADVERTISE_IPS': '172.18.0.5', 'JVB_PORT': '10000'},
                           'ports': [{'target': 10000, 'published': '10001', 'protocol': 'udp'}]}
        services['api'] = {'ports': [{'target': 9000, 'published': '9000'}]}
        r = self.audit(root=TOOLS.parents[2], mode='target', target={'MEDIA_HOST': '10.1.2.28'},
                       rendered={'services': services})
        self.assertGreaterEqual(len(r['errors']), 3)

    def test_credentials_are_never_logged(self):
        r = self.audit(root=TOOLS.parents[2], mode='generic', rendered={'services': {
            'web': {'environment': {'JWT_APP_SECRET': 'DO_NOT_LOG',
                                   'PUBLIC_URL': 'https://user:DO_NOT_LOG@example.org/?token=DO_NOT_LOG'}}}})
        self.assertNotIn('DO_NOT_LOG', json.dumps(r))
        self.assertTrue(r['errors'])

    def test_required_published_ports_are_exact(self):
        services = {s: {} for s in ['gateway', 'app-web', 'api', 'web', 'prosody', 'jicofo', 'jvb']}
        services['jvb'] = {'environment': {'JVB_ADVERTISE_IPS': '10.1.2.28', 'JVB_PORT': '10000'}}
        services['gateway'] = {'ports': [{'target': 443, 'published': '9444', 'protocol': 'udp'}]}
        report = self.audit(root=TOOLS.parents[2], mode='target', target={'MEDIA_HOST': '10.1.2.28'},
                            rendered={'services': services})
        self.assertTrue(any('gateway' in e for e in report['errors']))
        self.assertTrue(any('jvb' in e for e in report['errors']))

    def test_direct_entry_rejects_loopback_published_bindings(self):
        services={s:{} for s in ['gateway','app-web','api','web','prosody','jicofo','jvb']}
        services['gateway']={'ports':[{'published':'8443','target':443,'protocol':'tcp','host_ip':'127.0.0.1'},
                                      {'published':'8080','target':80,'protocol':'tcp'}]}
        services['jvb']={'ports':[{'published':'10000','target':10000,'protocol':'udp','host_ip':'127.0.0.1'}],
                         'environment':{'JVB_PORT':'10000','JVB_ADVERTISE_IPS':'10.1.2.28'}}
        report=self.audit(root=TOOLS.parents[2],mode='target',target={'MEDIA_HOST':'10.1.2.28'},rendered={'services':services})
        self.assertTrue(any('binding' in e for e in report['errors']))

    def test_external_target_is_explicit_and_outside_package(self):
        spec = importlib.util.spec_from_file_location('target', TOOLS.parent/'config/target.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)/'package'; root.mkdir()
            (root/'target.env').write_text('SITE_SCHEME=https\nHTTPS_PORT=443\nHTTP_PORT=80\nMEDIA_HOST=10.1.2.28\nMEDIA_PORT=10000\n', encoding='utf-8')
            instance = Path(temp)/'instance.env'
            instance.write_text((root/'target.env').read_text(encoding='utf-8').replace('MEDIA_HOST=10.1.2.28', 'MEDIA_HOST=10.1.2.28'), encoding='utf-8')
            self.assertEqual(module.resolve_target(root, instance)['JVB_ADVERTISE_IPS'], '10.1.2.28')
            with self.assertRaises(ValueError):
                module.resolve_target(root, root/'target.env')

    def test_cli_failure_retains_both_reports(self):
        import subprocess
        import sys
        with tempfile.TemporaryDirectory() as temp:
            result = subprocess.run([sys.executable, str(TOOLS/'network-audit.py'),
                '--root', str(TOOLS.parents[2]), '--mode', 'target', '--output', temp], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue((Path(temp)/'network-audit.json').is_file())
            self.assertTrue((Path(temp)/'network-audit.md').is_file())

    def test_source_inventory_redacts_url_and_records_network_consumers(self):
        spec = importlib.util.spec_from_file_location('network_audit', TOOLS/'network-audit.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp)
            (p/'application.properties').write_text('server.port=9000\nservice.url=https://u:PRIVATE_VALUE@example.org:9443/a?q=PRIVATE_VALUE\n')
            r = module.source_inventory(p, 'api')
            self.assertNotIn('PRIVATE_VALUE', json.dumps(r))
            self.assertTrue(any(x['value'] == 'https://example.org:9443/a' for x in r['parameters']))
            self.assertTrue(any(x['name'] == 'server.port' for x in r['parameters']))


if __name__ == '__main__':
    unittest.main()
