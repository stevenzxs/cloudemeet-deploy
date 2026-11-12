import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('target_config', ROOT/'config/target.py')
target = importlib.util.module_from_spec(spec)
spec.loader.exec_module(target)


class TargetTests(unittest.TestCase):
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
        text = (ROOT/'config/Caddyfile').read_text(encoding='utf-8')
        self.assertIn('https://:443', text)
        self.assertIn('fallback_sni cloudmeet.internal', text)
        self.assertNotIn('{$SITE_HOST}', text)
        self.assertNotIn('redir ', text)

    def test_derives_one_host_and_ports(self):
        values = target.load_target(ROOT/'config/target.env')
        self.assertNotIn('SERVER_HOST', values)
        self.assertEqual(values['JVB_ADVERTISE_IPS'], '')
        self.assertEqual(values['SITE_HOST'], 'cloudmeet.internal')

    def test_rejects_invalid_or_duplicate_values(self):
        text = (ROOT/'config/target.env').read_text(encoding='utf-8')
        for broken in (text+'\nSERVER_HOST=1.2.3.4\n', text+'\nPUBLIC_URL=https://old\n',
                       text.replace('8443', '8080'), text.replace('8443', '65536'),
                       text.replace('https', 'http')):
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory)/'target.env'
                path.write_text(broken)
                with self.assertRaises(ValueError):
                    target.load_target(path)

    def test_template_init_generates_secrets_only(self):
        import subprocess
        import sys
        import shutil
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(ROOT/'config', root/'config')
            subprocess.run([sys.executable, '-B', str(root/'config/init.py')], check=True, capture_output=True)
            values = target.read_env(root/'.env')
            self.assertEqual(set(values), {'JWT_APP_SECRET','JICOFO_AUTH_PASSWORD','JVB_AUTH_PASSWORD'})
            self.assertTrue(all(len(value)==64 for value in values.values()))
            before = (root/'.env').read_bytes()
            result = subprocess.run([sys.executable, '-B', str(root/'config/init.py')], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((root/'.env').read_bytes(), before)

    def test_other_target_changes_all_derived_addresses(self):
        text = (ROOT/'config/target.env').read_text(encoding='utf-8')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'target.env'
            path.write_text(text.replace('MEDIA_HOST=', 'MEDIA_HOST=192.0.2.8').replace('8443','9443'), encoding='utf-8')
            values = target.load_target(path)
            self.assertEqual(values['PUBLIC_URL'], 'https://cloudmeet.internal')
            self.assertEqual(values['SITE_HOST'], 'cloudmeet.internal')
            self.assertEqual(values['JVB_ADVERTISE_IPS'], '192.0.2.8')
