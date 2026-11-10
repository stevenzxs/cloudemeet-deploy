import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('enable',Path(__file__).parents[1]/'tools/enable-host-control.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class EnableTests(unittest.TestCase):
    def test_active_meeting_refuses_all_writes(self):
        with tempfile.TemporaryDirectory() as d, patch.object(module.subprocess,'check_output',
                return_value=json.dumps({'conferences':1,'participants':2}).encode()):
            with self.assertRaisesRegex(RuntimeError,'idle gate'):
                module.enable(d,'test')
            self.assertEqual(list(Path(d).iterdir()),[])

    def test_only_transfer_reclaim_flags_change_and_inode_preserved(self):
        with tempfile.TemporaryDirectory() as d, patch.object(module.subprocess,'check_output',
                return_value=json.dumps({'conferences':0,'participants':0}).encode()):
            root=Path(d)
            backup=root/'backups/host-control-test'
            backup.mkdir(parents=True)
            (backup/'api.sqlite.db').touch()
            config=root/'host-control/zz-cloudmeet-host-control.cfg.lua'
            config.parent.mkdir()
            original='host_transfer_enabled = false;\nhost_reclaim_enabled = false;\nhost_transfer_admin_recovery_enabled = false;\n'
            config.write_text(original)
            inode=config.stat().st_ino
            module.enable(root,'test')
            self.assertEqual(config.stat().st_ino,inode)
            self.assertIn('host_transfer_admin_recovery_enabled = false;',config.read_text())
            self.assertIn('host_transfer_enabled = true;',config.read_text())


if __name__=='__main__': unittest.main()
