import importlib.util
from pathlib import Path
import unittest
import tempfile
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('cert_tool', Path(__file__).with_name('cert-tool.py'))
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)

class CertificateTests(unittest.TestCase):
    def test_archive_members_permissions_and_digest(self):
        import tarfile
        import hashlib
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory)/'update';out.mkdir()
            for name in ('server.key','ca.crt','replace-cert.sh'):
                (out/name).write_bytes(name.encode())
            tool.write_checksums(out)
            archive=tool.write_archive(out)
            with tarfile.open(archive) as tar:
                members={m.name:m for m in tar.getmembers()}
                self.assertEqual(set(members),{'update'}|{'update/'+p.name for p in out.iterdir()})
                self.assertEqual(members['update/server.key'].mode,0o600)
                self.assertEqual(members['update/replace-cert.sh'].mode,0o755)
                self.assertEqual(tar.extractfile('update/server.key').read(),b'server.key')
            self.assertEqual(Path(str(archive)+'.sha256').read_text(),
                             hashlib.sha256(archive.read_bytes()).hexdigest()+'  '+archive.name+'\n')
            with self.assertRaises(FileExistsError): tool.write_archive(out)

    def test_archive_rejects_ca_private_key_and_unlisted_files(self):
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory)/'update';out.mkdir();(out/'ca.key').write_bytes(b'secret')
            tool.write_checksums(out)
            with self.assertRaises(ValueError): tool.write_archive(out)
            (out/'ca.key').unlink();tool.write_checksums(out)
            (out/'unexpected').write_bytes(b'unlisted')
            with self.assertRaises(ValueError): tool.write_archive(out)

    def test_fixed_tags_preserve_internal_and_routes_on_renewal(self):
        source = {'apps': {'tls': {'certificates': {'load_files': [
            {'certificate': '/config/old/server.crt', 'key': '/config/old/server.key', 'tags': ['cert0']},
            {'certificate': '/host-control/gateway.crt', 'key': '/host-control/gateway.key', 'tags': ['cert1']},
        ]}}, 'http': {'servers': {
            'external': {'listen': [':443'], 'routes': [{'unchanged': True}],
                         'tls_connection_policies': [{'certificate_selection': {'any_tag': ['cert0']}}]},
            'internal': {'listen': [':9443'], 'tls_connection_policies': [{}, {}]},
        }}}}
        import copy
        original = copy.deepcopy(source)
        result = tool.fixed_tls_json(source, '/config/cloudmeet-cert/new')
        self.assertEqual(source, original)
        files = result['apps']['tls']['certificates']['load_files']
        self.assertEqual(files[0]['tags'], ['cert'])
        self.assertEqual(files[1]['tags'], ['cert-inner'])
        renewed = tool.fixed_tls_json(result, '/config/cloudmeet-cert/renewed')
        self.assertEqual(renewed['apps']['tls']['certificates']['load_files'][1], files[1])
        self.assertEqual(renewed['apps']['http'], result['apps']['http'])
        for policy in result['apps']['http']['servers']['internal']['tls_connection_policies']:
            self.assertEqual(policy['certificate_selection'], {'any_tag': ['cert-inner']})

    def test_fixed_tags_reject_unknown_layout(self):
        with self.assertRaises(ValueError):
            tool.fixed_tls_json({'apps': {}}, '/config/cloudmeet-cert/new')

    def test_issue_includes_ip_and_default_sni_without_new_ca(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); ca=root/'ca';ca.mkdir();(ca/'ca.crt').write_bytes(b'original CA')
            out=root/'issued'
            with patch('sys.argv', ['cert-tool.py','issue','--ca-directory',str(ca),
                       '--ips','47.96.221.94','--output',str(out)]), patch.object(tool,'run') as run:
                tool.main()
            self.assertIn('subjectAltName=IP:47.96.221.94,DNS:cloudmeet.internal',
                          (out/'extensions.cnf').read_text())
            self.assertEqual((out/'ca.crt').read_bytes(),b'original CA')
            self.assertFalse((out/'ca.key').exists())
            self.assertEqual((out/'restart-verify-gateway.sh').read_bytes(),
                             Path(__file__).with_name('restart-verify-gateway.sh').read_bytes())
            self.assertIn('  restart-verify-gateway.sh\n', (out/'SHA256SUMS').read_text())
            self.assertTrue(any('-verify_hostname' in c.args and 'cloudmeet.internal' in c.args
                                for c in run.call_args_list))
    def test_checksum_manifest_uses_literal_lf_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'ca.crt').write_bytes(b'certificate\r\n')
            tool.write_checksums(root)
            raw = (root/'SHA256SUMS').read_bytes()
            self.assertNotIn(b'\r', raw)
            self.assertTrue(raw.endswith(b'  ca.crt\n'))
            tool.write_checksums(root)
            self.assertEqual((root/'SHA256SUMS').read_bytes(), raw)

    def test_ip_validation(self):
        self.assertEqual(tool.ip_list('47.96.221.94,192.168.1.10'), ['47.96.221.94', '192.168.1.10'])
        for value in ['bad', '1.2.3.999', '127.0.0.1;echo x', '::1']:
            with self.assertRaises(ValueError):
                tool.ip_list(value)

    def test_only_expected_tls_directives_changed(self):
        source = Path(__file__).parents[1].joinpath('config/Caddyfile').read_text()
        updated = tool.external_tls(source, '/config/cloudmeet-cert/example')
        self.assertNotIn('tls internal', updated)
        self.assertEqual(updated.count('tls /config/cloudmeet-cert/example/server.crt /config/cloudmeet-cert/example/server.key'), 2)
        self.assertIn('reverse_proxy app-web:80', updated)
        renewed = tool.external_tls(updated, '/config/cloudmeet-cert/new')
        self.assertEqual(renewed.count('tls /config/cloudmeet-cert/new/server.crt /config/cloudmeet-cert/new/server.key'), 2)
        with self.assertRaises(ValueError):
            tool.external_tls('https://:443 { tls custom }', '/config/example')

if __name__ == '__main__':
    unittest.main()
