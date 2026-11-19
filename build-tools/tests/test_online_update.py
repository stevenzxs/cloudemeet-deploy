import importlib.util
from pathlib import Path
import unittest


class OnlineUpdateTests(unittest.TestCase):
    def module(self):
        path=Path(__file__).parents[1]/'offline-runtime/online_update.py'
        self.assertTrue(path.exists(),'Missing existing-instance update entry')
        spec=importlib.util.spec_from_file_location('online_update',path)
        mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        return mod

    def test_only_complete_pinned_seven_service_publication_accepted(self):
        m=self.module()
        images={s:{'reference':'ghcr.io/stevenzxs/cloudmeet-'+s+'@sha256:'+'a'*64,
                   'image_id':'sha256:'+'b'*64,'platform':'linux/amd64'} for s in m.SERVICES}
        record={'status':'PUBLISHED_NOT_DEPLOYED','architecture':'amd64','images':images}
        m.validate_registry(record)
        images['api']['reference']='ghcr.io/stevenzxs/cloudmeet-api:latest'
        with self.assertRaises(ValueError):m.validate_registry(record)

    def test_incomplete_publication_rejected(self):
        m=self.module()
        with self.assertRaises(ValueError):m.validate_registry({'status':'PUBLISHING_NOT_COMPLETE'})

    def test_override_changes_images_only(self):
        m=self.module()
        record={'images':{s:{'reference':'digest-'+s} for s in m.SERVICES}}
        override=m.image_override(record)
        self.assertEqual(set(override),{'services'})
        self.assertEqual(override['services']['api'],{'image':'digest-api','pull_policy':'never'})

    def test_current_jvb_stats_idle_contract(self):
        m=self.module()
        self.assertTrue(m.is_idle({'conferences':{}}))
        self.assertFalse(m.is_idle({'conferences':{'abc':{}}}))
        self.assertFalse(m.is_idle({}))

    def test_update_refuses_changed_product_patches(self):
        m=self.module()
        old={'patches':{'patches/web/custom.css':'a'}}
        new={'patches':{'patches/web/custom.css':'b'}}
        with self.assertRaises(ValueError):m.require_compatible_material(old,new)
        m.require_compatible_material(old,old)


if __name__=='__main__':unittest.main()
