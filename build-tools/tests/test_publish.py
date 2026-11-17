import importlib.util
from pathlib import Path
import unittest
import subprocess
from unittest.mock import patch


class PublicationTests(unittest.TestCase):
    def test_unknown_blob_retries_same_image_but_auth_never_retries(self):
        spec=importlib.util.spec_from_file_location('publish',Path(__file__).parents[1]/'publish.py')
        mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        bad=subprocess.CompletedProcess([],1,'','unknown blob')
        good=subprocess.CompletedProcess([],0,'pushed','')
        with patch.object(mod.subprocess,'run',side_effect=[bad,good]) as run, patch.object(mod,'require_absent') as absent, patch.object(mod.time,'sleep'):
            mod.push_exact('fixture')
            self.assertEqual(run.call_count,2)
            self.assertEqual(run.call_args_list[0],run.call_args_list[1])
            absent.assert_called_once_with('fixture')
        with patch.object(mod.subprocess,'run',return_value=subprocess.CompletedProcess([],1,'','denied: write_package')) as run:
            with self.assertRaises(subprocess.CalledProcessError):mod.push_exact('fixture')
            self.assertEqual(run.call_count,1)
        with patch.object(mod.subprocess,'run',return_value=bad) as run, patch.object(mod,'require_absent'), patch.object(mod.time,'sleep'):
            with self.assertRaises(subprocess.CalledProcessError):mod.push_exact('fixture')
            self.assertEqual(run.call_count,3)
        with patch.object(mod.subprocess,'run',return_value=bad) as run, patch.object(mod,'require_absent',side_effect=ValueError('Existing tag')):
            with self.assertRaises(ValueError):mod.push_exact('fixture')
            self.assertEqual(run.call_count,1)

    def test_registry_absence_probe_fails_closed_and_preserves_diagnostics(self):
        spec=importlib.util.spec_from_file_location('publish',Path(__file__).parents[1]/'publish.py')
        mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        remote='ghcr.io/stevenzxs/cloudmeet-gateway:fixture'
        for message in ('unauthorized','denied','connection timed out','unknown: authentication required'):
            with self.subTest(message=message), patch.object(mod.subprocess,'run',return_value=subprocess.CompletedProcess([],1,'',message)):
                with self.assertRaisesRegex(RuntimeError,message):mod.require_absent(remote)
        with patch.object(mod.subprocess,'run',return_value=subprocess.CompletedProcess([],1,'','manifest unknown')):
            mod.require_absent(remote)
        with patch.object(mod.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'{}','')):
            with self.assertRaises(ValueError):mod.require_absent(remote)

    def test_workflow_requires_explicit_publication_after_package(self):
        text=(Path(__file__).parents[2]/'.github/workflows/build-package.yml').read_text()
        self.assertIn('publish_images:',text)
        self.assertIn('needs: [build, package]',text)
        self.assertIn('packages: write',text)
        self.assertIn('inputs.publish_images',text)

    def test_registry_manifest_binds_config_identity(self):
        path=Path(__file__).parents[1]/'publish.py'
        self.assertTrue(path.exists(),'Missing exact-image publication implementation')
        spec=importlib.util.spec_from_file_location('publish',path)
        mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        image='sha256:'+'a'*64
        manifest={'schemaVersion':2,'config':{'digest':image},'layers':[]}
        self.assertTrue(mod.matches_config(manifest,image))
        self.assertFalse(mod.matches_config(manifest,'sha256:'+'b'*64))
        self.assertFalse(mod.matches_config({'manifests':[]},image))


if __name__=='__main__': unittest.main()
