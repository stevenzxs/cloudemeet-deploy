"""Source-image runtime preparation must not reuse old shadow artifacts."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import os
import shutil
from unittest.mock import patch


class StartTests(unittest.TestCase):
    def test_runtime_environment_discards_parent_overrides(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            shutil.copyfile(Path(__file__).parents[2]/'config/target.py',root/'target.py')
            shutil.copyfile(Path(__file__).parents[2]/'config/target.env',root/'target.env')
            (root/'jitsi.env').write_text('ENABLE_AUTH=1\n')
            keys=('JWT_APP_SECRET','JICOFO_AUTH_PASSWORD','JVB_AUTH_PASSWORD','JITSI_ROLE_CHECK_SECRET')
            (root/'.env').write_text(''.join(k+'=generated\n' for k in keys))
            with patch.dict(os.environ,{'JWT_APP_SECRET':'stale','ENABLE_AUTH':'0','COMPOSE_FILE':'evil.yaml'}):
                env=self.module.runtime_environment(root)
                self.assertEqual(env['JWT_APP_SECRET'],'generated')
                self.assertEqual(env['ENABLE_AUTH'],'1')
                self.assertNotIn('COMPOSE_FILE',env)
                self.assertEqual(os.environ['JWT_APP_SECRET'],'stale')

    def test_target_fingerprint_rejects_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            spec=importlib.util.spec_from_file_location('target',Path(__file__).parents[2]/'config/target.py')
            target=importlib.util.module_from_spec(spec);spec.loader.exec_module(target)
            shutil.copyfile(Path(__file__).parents[2]/'config/target.env',root/'target.env')
            with patch.dict(os.environ,{'CLOUDMEET_TARGET_SHA256':'0'*64}):
                with self.assertRaisesRegex(ValueError,'changed'):
                    target.resolve_target(root)
    def test_transfer_and_creator_reclaim_enabled_together(self):
        source=(Path(__file__).parents[1]/'offline-runtime/start.py').read_text()
        self.assertIn('host_transfer_enabled = true;',source)
        self.assertIn('host_reclaim_enabled = true;',source)
        self.assertIn("'host_reclaim_url':'reclaim'",source)
        self.assertIn('host_transfer_admin_recovery_enabled = false;',source)

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
            with self.subTest('OpenSSL may omit serial sidecar'):
                serial=root/'data/host-control/ca.srl'
                if serial.exists():
                    serial.unlink()
                self.module.require_instance(root)
            with self.subTest('unexpected TLS file rejected'):
                extra=root/'data/host-control/unexpected'
                extra.write_text('unexpected')
                with self.assertRaises(ValueError): self.module.require_instance(root)
                extra.unlink()
            with self.subTest('business data rejected'):
                (root/'data/api').mkdir()
                with self.assertRaises(ValueError): self.module.require_instance(root)
                (root/'data/api').rmdir()
            with self.subTest('missing key rejected'):
                (root/'data/host-control/gateway.key').unlink()
                with self.assertRaises(ValueError): self.module.require_instance(root)

    def test_registry_start_uses_bound_manifest_identity(self):
        import hashlib
        import shutil
        from unittest.mock import patch
        config='sha256:'+'a'*64
        raw=json.dumps({'schemaVersion':2,'config':{'digest':config}}).encode()
        digest='sha256:'+hashlib.sha256(raw).hexdigest()
        services=('gateway','app-web','api','web','prosody','jicofo','jvb')
        manifest={'batch':'batch','deployment_commit':'commit','architecture':'amd64',
                  'image_transport':'registry','images':{s:[s,config] for s in services}}
        registry={'batch':'batch','configuration_commit':'commit','architecture':'amd64',
                  'status':'PUBLISHED_NOT_DEPLOYED','images':{s:{'image_id':config,
                  'reference':'ghcr.io/stevenzxs/cloudmeet-'+s+'@'+digest,'platform':'linux/amd64'} for s in services}}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for name in ('deploy.py','image_transport.py'):
                shutil.copyfile(Path(__file__).parents[1]/'offline-runtime'/name,root/name)
            def inspect(command):
                service=command[-1]
                return json.dumps([{'Id':digest,'Descriptor':{'digest':digest},
                    'RepoDigests':[registry['images'][service]['reference']],
                    'Os':'linux','Architecture':'amd64'}]).encode()
            with patch.object(self.module.subprocess,'check_output',side_effect=inspect), patch('urllib.request.build_opener') as opener:
                response=opener.return_value.open.return_value.__enter__.return_value
                response.read.side_effect=[value for _ in services for value in (b'{"token":"fixture"}',raw)]
                self.module.validate_local_images(root,manifest,registry)
            bad=dict(registry,configuration_commit='wrong')
            with self.assertRaises(ValueError):self.module.validate_local_images(root,manifest,bad)
            with self.assertRaises(ValueError):self.module.validate_local_images(root,manifest)

    def test_start_uses_shared_archive_bound_identity_check(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            import shutil
            shutil.copyfile(Path(__file__).parents[1]/'offline-runtime/deploy.py',root/'deploy.py')
            manifest={'architecture':'amd64','images':{'gateway':['tag','sha256:config']},
                      'image_archives':{'gateway':{'file':'gateway.tar.gz'}}}
            info={'Id':'sha256:config','Os':'linux','Architecture':'amd64'}
            with patch.object(self.module.subprocess,'check_output',return_value=json.dumps([info]).encode()):
                self.module.validate_local_images(root,manifest)
            info['Architecture']='arm64'
            with patch.object(self.module.subprocess,'check_output',return_value=json.dumps([info]).encode()):
                with self.assertRaises(ValueError): self.module.validate_local_images(root,manifest)

if __name__=='__main__': unittest.main()
