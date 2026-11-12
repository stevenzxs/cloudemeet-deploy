import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('target_config', ROOT/'deploy/config/target.py')
target = importlib.util.module_from_spec(spec)
spec.loader.exec_module(target)


class TargetTests(unittest.TestCase):
    def test_derives_one_host_and_ports(self):
        values = target.load_target(ROOT/'deploy/config/target.env')
        self.assertEqual(values['SITE_HOST'], values['SERVER_HOST'])
        self.assertEqual(values['JVB_ADVERTISE_IPS'], values['SERVER_HOST'])
        self.assertEqual(values['PUBLIC_URL'], 'https://' + values['SERVER_HOST'] + ':' + values['HTTPS_PORT'])

    def test_rejects_invalid_or_duplicate_values(self):
        text = (ROOT/'deploy/config/target.env').read_text(encoding='utf-8')
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
            shutil.copytree(ROOT/'deploy/config', root/'config')
            subprocess.run([sys.executable, '-B', str(root/'config/init.py')], check=True, capture_output=True)
            values = target.read_env(root/'.env')
            self.assertEqual(set(values), {'JWT_APP_SECRET','JICOFO_AUTH_PASSWORD','JVB_AUTH_PASSWORD'})
            self.assertTrue(all(len(value)==64 for value in values.values()))
            before = (root/'.env').read_bytes()
            result = subprocess.run([sys.executable, '-B', str(root/'config/init.py')], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((root/'.env').read_bytes(), before)

    def test_other_target_changes_all_derived_addresses(self):
        text = (ROOT/'deploy/config/target.env').read_text(encoding='utf-8')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'target.env'
            original = target.load_target(ROOT/'deploy/config/target.env')
            path.write_text(text.replace(original['SERVER_HOST'], '192.0.2.8').replace('8443','9443'), encoding='utf-8')
            values = target.load_target(path)
            self.assertEqual(values['PUBLIC_URL'], 'https://192.0.2.8:9443')
            self.assertEqual(values['SITE_HOST'], '192.0.2.8')
            self.assertEqual(values['JVB_ADVERTISE_IPS'], '192.0.2.8')
