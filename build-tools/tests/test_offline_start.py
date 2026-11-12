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

    def test_initialization_then_first_start_preserves_internal_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            path=Path(__file__).parents[1]/'offline-runtime/initialize.py'
            spec=importlib.util.spec_from_file_location('initialize',path)
            initialize=importlib.util.module_from_spec(spec); spec.loader.exec_module(initialize)
            initialize.initialize_host_control(root)
            (root/'candidate.json').write_text(json.dumps({'status':'PACKAGED'}))
            (root/'.env').write_text('secret=preserved\n'); (root/'.env').chmod(0o600)
            before={p.name:p.read_bytes() for p in (root/'data/host-control').iterdir()}
            self.module.require_instance(root)
            self.assertEqual(before,{p.name:p.read_bytes() for p in (root/'data/host-control').iterdir()})
            with self.subTest('business data rejected'):
                (root/'data/api').mkdir()
                with self.assertRaises(ValueError): self.module.require_instance(root)
                (root/'data/api').rmdir()
            with self.subTest('missing key rejected'):
                (root/'data/host-control/gateway.key').unlink()
                with self.assertRaises(ValueError): self.module.require_instance(root)

if __name__=='__main__': unittest.main()
