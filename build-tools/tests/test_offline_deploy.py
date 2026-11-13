"""Exercise installation control flow without changing the build host."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch


class DeployTests(unittest.TestCase):
    def setUp(self):
        path=Path(__file__).parents[1]/'offline-runtime/deploy.py'
        self.assertTrue(path.exists(),'Missing offline execution entry')
        spec=importlib.util.spec_from_file_location('offline_deploy',path)
        self.mod=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)

    def test_incomplete_candidate_never_executes_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'candidate.json').write_text(json.dumps({'status':'INCOMPLETE_NOT_FOR_INSTALL'}))
            verifier=Mock(); verifier.require_ready.side_effect=ValueError('Incomplete')
            runner=Mock()
            with self.assertRaises(ValueError): self.mod.deploy(root,verifier,runner)
            runner.assert_not_called()

    def test_existing_data_never_executes_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'data').mkdir()
            (root/'candidate.json').write_text('{}')
            runner=Mock()
            with self.assertRaises(ValueError): self.mod.deploy(root,Mock(),runner)
            runner.assert_not_called()

    def test_host_mismatch_never_executes_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'candidate.json').write_text('{}')
            verifier=Mock(); verifier.require_target.side_effect=ValueError('Wrong host')
            runner=Mock()
            with self.assertRaises(ValueError): self.mod.deploy(root,verifier,runner)
            runner.assert_not_called()

    def test_conflicting_image_tag_is_rejected(self):
        with self.assertRaises(ValueError):
            self.mod.check_local_identity({'Id':'sha256:wrong'},'sha256:approved')
        self.mod.check_local_identity(None,'sha256:approved')
        self.mod.check_local_identity({'Id':'sha256:approved','Os':'linux','Architecture':'amd64'},'sha256:approved')

    def test_explicit_arm_image_identity(self):
        self.mod.check_local_identity({'Id':'sha256:approved','Os':'linux','Architecture':'arm64'},
                                      'sha256:approved', 'arm64')
        with self.assertRaises(ValueError):
            self.mod.check_local_identity({'Id':'sha256:approved','Os':'linux','Architecture':'amd64'},
                                          'sha256:approved', 'arm64')

    def test_containerd_manifest_identity_is_bound_to_archive_config(self):
        import hashlib
        import io
        import tarfile
        raw=json.dumps({'schemaVersion':2,'config':{'digest':'sha256:approved'}}).encode()
        digest='sha256:'+hashlib.sha256(raw).hexdigest()
        with tempfile.TemporaryDirectory() as tmp:
            archive=Path(tmp)/'image.tar.gz'
            with tarfile.open(archive,'w:gz') as tar:
                member=tarfile.TarInfo('blobs/sha256/'+digest.split(':')[1]); member.size=len(raw)
                tar.addfile(member,io.BytesIO(raw))
                index=json.dumps({'manifests':[{'digest':digest}]}).encode()
                member=tarfile.TarInfo('index.json'); member.size=len(index)
                tar.addfile(member,io.BytesIO(index))
            info={'Id':digest,'Os':'linux','Architecture':'amd64'}
            self.mod.check_local_identity(info,'sha256:approved','amd64',archive)
            with self.assertRaises(ValueError):
                self.mod.check_local_identity(info,'sha256:other','amd64',archive)
            with self.assertRaises(ValueError):
                self.mod.check_local_identity(dict(info,Id='sha256:wrong'),'sha256:approved','amd64',archive)
            with self.assertRaises(ValueError):
                self.mod.check_local_identity(info,'sha256:approved','arm64',archive)

    def test_archive_set_missing_prevents_any_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'candidate.json').write_text(json.dumps({'images':{'jvb':['tag','sha256:approved']}}))
            verifier=Mock(); verifier.compose_prefix.return_value=['docker','compose']
            runner=Mock(return_value=Mock(returncode=0,stdout='linux/amd64'))
            with patch.object(self.mod.os,'geteuid',return_value=0):
                with self.assertRaises(ValueError): self.mod.deploy(root,verifier,runner)
            self.assertFalse(any('load' in call.args[0] for call in runner.call_args_list))

    def test_load_identity_mismatch_prevents_initialize(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'images').mkdir(); (root/'images/jvb.gz').write_bytes(b'image')
            record={'tag':'tag','image_id':'sha256:approved','file':'jvb.gz','bytes':5,'sha256':'digest'}
            (root/'candidate.json').write_text(json.dumps({'images':{'jvb':['tag','sha256:approved']},'image_archives':{'jvb':record}}))
            verifier=Mock(); verifier.sha256_file.return_value='digest'
            verifier.compose_prefix.return_value=['docker','compose']
            responses=[Mock(returncode=0,stdout='linux/amd64'),Mock(),Mock(returncode=1,stdout=''),Mock(),
                       Mock(returncode=0,stdout=json.dumps([{'Id':'sha256:wrong'}]))]
            runner=Mock(side_effect=responses)
            with patch.object(self.mod.os,'geteuid',return_value=0):
                with self.assertRaises(ValueError): self.mod.deploy(root,verifier,runner)
            self.assertFalse(any(any('initialize.py' in arg for arg in call.args[0]) for call in runner.call_args_list))


if __name__=='__main__': unittest.main()
