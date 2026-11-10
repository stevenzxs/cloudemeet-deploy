import importlib.util
import io
from pathlib import Path
import hashlib
import tarfile
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('stageweb',Path(__file__).parents[1]/'tools/stage-host-control-web.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class WebTests(unittest.TestCase):
    def test_digest_mismatch_refuses_writes(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); archive=root/'a.tar';archive.write_bytes(b'bad')
            with self.assertRaisesRegex(RuntimeError,'digest'):module.stage(root,archive,'wrong')
            self.assertFalse((root/'host-control').exists())

    def test_stage_overlay_without_service_actions(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'host-control').mkdir();archive=root/'a.tar'
            with tarfile.open(archive,'w') as t:
                info=tarfile.TarInfo('index.html');info.size=2;t.addfile(info,io.BytesIO(b'ok'))
            module.stage(root,archive,hashlib.sha256(archive.read_bytes()).hexdigest())
            self.assertEqual((root/'host-control/web-candidate/index.html').read_text(),'ok')
            self.assertIn('/usr/share/nginx/html/cm:ro',(root/'host-control/web-compose.json').read_text())
