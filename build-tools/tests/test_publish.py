import importlib.util
from pathlib import Path
import unittest


class PublicationTests(unittest.TestCase):
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
