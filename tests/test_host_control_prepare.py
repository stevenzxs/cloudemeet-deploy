import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('prepare', Path(__file__).parents[1]/'tools/prepare-host-control.py')
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


class PrepareTests(unittest.TestCase):
    def test_existing_configuration_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/'host-control').mkdir()
            with self.assertRaisesRegex(RuntimeError, 'already exists'):
                prepare.prepare(d, 'prosody')

    def test_output_is_disabled_private_and_has_no_published_port(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root/'.env').write_text('existing-secret=not-modified')
            with patch.object(prepare.subprocess, 'check_output', side_effect=[
                    'Include "conf.d/*.cfg.lua"', '1234 1235',
                    json.dumps([{'Config': {'Env': ['XMPP_MUC_MODULES=existing_module']}}])]), \
                 patch.object(prepare.subprocess, 'run') as run, patch.object(prepare.os, 'chown', create=True):
                prepare.prepare(root, 'prosody')
            out = root/'host-control'
            cfg = (out/'zz-cloudmeet-host-control.cfg.lua').read_text()
            self.assertIn('host_transfer_enabled = false', cfg)
            self.assertIn('host_transfer_admin_recovery_enabled = false', cfg)
            overlay = json.loads((out/'compose.json').read_text())
            self.assertTrue(all('ports' not in s for s in overlay['services'].values()))
            self.assertEqual(overlay['services']['prosody']['environment']['XMPP_MUC_MODULES'],
                             'existing_module,muc_jwt_owner,muc_host_transfer')
            self.assertEqual(overlay['services']['api']['env_file'], ['./host-control/api.env'])
            self.assertIn('verify = "peer"', (out/'prosody.cfg.lua').read_text())
            self.assertIn('api:9000', (out/'gateway-internal.caddy').read_text())
            self.assertIn('rewrite * /mapi{uri}', (out/'gateway-internal.caddy').read_text())
            self.assertEqual((root/'.env').read_text(), 'existing-secret=not-modified')
            self.assertEqual(len(run.call_args_list), 3)


if __name__ == '__main__':
    unittest.main()
