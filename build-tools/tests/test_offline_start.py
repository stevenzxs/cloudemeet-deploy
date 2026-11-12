"""Source-image runtime preparation must not reuse old shadow artifacts."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


class StartTests(unittest.TestCase):
    def setUp(self):
        path=Path(__file__).parents[1]/'offline-runtime/start.py'
        spec=importlib.util.spec_from_file_location('start',path)
        self.module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

    def test_compose_inputs_explicit_and_never_pull(self):
        command=self.module.compose_command(Path('/bundle'))
        self.assertEqual(command.count('-f'),3)
        self.assertIn('/bundle/source-images.yaml',command)
        self.assertNotIn('pull',command)

    def test_incomplete_manifest_blocks_preparation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'candidate.json').write_text(json.dumps({'status':'INCOMPLETE_NOT_FOR_INSTALL'}))
            with self.assertRaises(ValueError): self.module.require_instance(root)
            self.assertFalse((root/'data').exists())

    def test_external_data_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'outside').mkdir()
            (root/'data').symlink_to(root/'outside',target_is_directory=True)
            with self.assertRaises(ValueError): self.module.safe_directory(root,'data/jitsi')
            self.assertFalse((root/'outside/jitsi').exists())

    def test_safe_directory_created_only_within_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            self.module.safe_directory(root,'data/jitsi/web')
            self.assertTrue((root/'data/jitsi/web').is_dir())
            with self.assertRaises(ValueError): self.module.safe_directory(root,'../outside')

if __name__=='__main__': unittest.main()
