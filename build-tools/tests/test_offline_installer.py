"""Installer integrity checks must execute before any system mutation."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
import ast

class InstallerTests(unittest.TestCase):
    def test_packaged_contract_does_not_require_installation_evidence(self):
        images = {name: ['sha256:' + str(i) * 64, 'sha256:' + str(i) * 64]
                  for i, name in enumerate(sorted(self.mod.SERVICES), 1)}
        manifest = {'status': 'PACKAGED', 'package_contract': 1, 'architecture': 'arm64',
                    'images': images, 'image_archives': {name: {} for name in images},
                    'requires': ['existing Docker Engine'],
                    'compose': {'file': 'bin/docker-compose', 'sha256': 'a' * 64}}
        self.mod.require_ready(manifest)
        manifest.pop('compose')
        with self.assertRaises(ValueError):
            self.mod.require_ready(manifest)

    def test_generic_arm_profile_checks_architecture_not_distro_name(self):
        from unittest.mock import patch
        with patch.object(self.mod.platform, 'system', return_value='Linux'):
            self.mod.require_target({'ID': 'kylin', 'VERSION_ID': 'V10'}, 'aarch64',
                                    'linux-aarch64-existing-engine')
            self.mod.require_target({'ID': 'ubuntu', 'VERSION_ID': '24.04'}, 'aarch64',
                                    'linux-aarch64-existing-engine')
        with self.assertRaises(ValueError):
            self.mod.require_target({}, 'x86_64', 'linux-aarch64-existing-engine')

    def test_explicit_kylin_aarch64_profile(self):
        self.mod.require_target({'ID': 'kylin', 'VERSION_ID': 'V10'}, 'aarch64',
                                'kylin-v10-aarch64-existing-engine')
        for os_info, arch in [({'ID': 'ubuntu', 'VERSION_ID': '22.04'}, 'aarch64'),
                              ({'ID': 'kylin', 'VERSION_ID': 'V10'}, 'x86_64')]:
            with self.assertRaises(ValueError):
                self.mod.require_target(os_info, arch, 'kylin-v10-aarch64-existing-engine')
        with self.assertRaises(ValueError):
            self.mod.require_target({'ID': 'kylin', 'VERSION_ID': 'V10'}, 'aarch64', 'unknown')

    def product_fixture(self, root):
        for name in self.mod.PRODUCT_PATCHES:
            p = root / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('fixture')
        return {'services': {
            'prosody': {'environment': {'ENABLE_AUTH': '1', 'AUTH_TYPE': 'jwt',
                'JWT_APP_ID': 'fixture', 'JWT_APP_SECRET': 'fixture-secret',
                'XMPP_DOMAIN': 'meet.jitsi', 'XMPP_MUC_MODULES': 'muc_jwt_owner'}},
            'jicofo': {'environment': {'ENABLE_AUTO_OWNER': '0'}},
            'api': {'environment': {'JITSI_TOKEN_APP_ID': 'fixture',
                'JITSI_TOKEN_APP_SECRET': 'fixture-secret', 'JITSI_TOKEN_DOMAIN': 'meet.jitsi'}}}}

    def test_missing_product_patch_rejected_independent_of_checksums(self):
        self.assertEqual(set(self.mod.PRODUCT_PATCHES), {
            'patches/web/custom-interface_config.js', 'patches/web/custom-head.html',
            'patches/web/custom.css', 'patches/web/nginx-custom/custom-css.conf',
            'patches/prosody/mod_muc_jwt_owner.lua'})
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = self.product_fixture(root)
            for name in self.mod.PRODUCT_PATCHES:
                p = root / name
                p.unlink()
                with self.assertRaisesRegex(ValueError, 'Missing product patch'):
                    self.mod.verify_product(root, config)
                p.write_text('fixture')

    def test_product_rejects_auth_module_auto_owner_and_jwt_mismatch(self):
        import copy
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = self.product_fixture(root)
            self.mod.verify_product(root, config)
            for service, key, value in [('prosody', 'ENABLE_AUTH', '0'),
                    ('prosody', 'AUTH_TYPE', 'internal'),
                    ('prosody', 'XMPP_MUC_MODULES', ''),
                    ('jicofo', 'ENABLE_AUTO_OWNER', '1'),
                    ('api', 'JITSI_TOKEN_DOMAIN', 'wrong'),
                    ('api', 'JITSI_TOKEN_APP_SECRET', 'wrong')]:
                bad = copy.deepcopy(config)
                bad['services'][service]['environment'][key] = value
                with self.assertRaises(ValueError):
                    self.mod.verify_product(root, bad)

    def test_target_scripts_parse_on_python37(self):
        runtime = Path(__file__).parents[1] / 'offline-runtime'
        for name in ['install.py', 'deploy.py', 'start.py']:
            ast.parse((runtime / name).read_text(), filename=name, feature_version=(3, 7))

    def test_integrity_check_does_not_need_python39_path_api(self):
        source = (Path(__file__).parents[1] / 'offline-runtime/install.py').read_text()
        self.assertNotIn('.is_relative_to(', source)

    def setUp(self):
        path=Path(__file__).parents[1]/'offline-runtime/install.py'
        self.assertTrue(path.exists(),'Missing offline installer')
        spec=importlib.util.spec_from_file_location('installer',path)
        self.mod=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)
    def test_checksums_accept_exact_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'payload').write_bytes(b'good')
            (root/'SHA256SUMS').write_text(hashlib.sha256(b'good').hexdigest()+'  payload\n')
            self.mod.verify_checksums(root)
    def test_tampering_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'payload').write_bytes(b'bad')
            (root/'SHA256SUMS').write_text(hashlib.sha256(b'good').hexdigest()+'  payload\n')
            with self.assertRaises(ValueError): self.mod.verify_checksums(root)
    def test_path_escape_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'SHA256SUMS').write_text('0'*64+'  ../outside\n')
            with self.assertRaises(ValueError): self.mod.verify_checksums(root)
    def test_incomplete_candidate_cannot_install(self):
        with self.assertRaises(ValueError): self.mod.require_ready({'status':'INCOMPLETE_NOT_FOR_INSTALL'})
    def test_ready_requires_seven_unique_images(self):
        with self.assertRaises(ValueError): self.mod.require_ready({'status':'READY_FOR_INSTALL','images':{}})
    def test_unlisted_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'payload').write_bytes(b'good'); (root/'extra').write_text('extra')
            (root/'SHA256SUMS').write_text(hashlib.sha256(b'good').hexdigest()+'  payload\n')
            with self.assertRaises(ValueError): self.mod.verify_checksums(root)
    def test_nested_checksum_file_is_not_exempt_from_inventory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'payload').write_bytes(b'good')
            (root/'nested').mkdir(); (root/'nested/SHA256SUMS').write_text('unlisted')
            (root/'SHA256SUMS').write_text(hashlib.sha256(b'good').hexdigest()+'  payload\n')
            with self.assertRaises(ValueError): self.mod.verify_checksums(root)
    def test_symlink_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'real').mkdir(); (root/'real/payload').write_bytes(b'good')
            (root/'alias').symlink_to(root/'real',target_is_directory=True)
            digest=hashlib.sha256(b'good').hexdigest()
            (root/'SHA256SUMS').write_text(digest+'  real/payload\n'+digest+'  alias/payload\n')
            with self.assertRaises(ValueError): self.mod.verify_checksums(root)
    def test_target_os_must_match(self):
        self.mod.require_target({'ID':'ubuntu','VERSION_ID':'22.04'},'x86_64')
        for osinfo,arch in [({'ID':'ubuntu','VERSION_ID':'24.04'},'x86_64'),
                            ({'ID':'ubuntu','VERSION_ID':'22.04'},'aarch64')]:
            with self.assertRaises(ValueError): self.mod.require_target(osinfo,arch)
    def test_dependency_plan_cannot_download(self):
        command=self.mod.dependency_command([Path('/bundle/dependencies/docker.deb')],simulate=True)
        self.assertIn('--no-download',command)
        self.assertIn('--simulate',command)
        self.assertNotIn('update',command)
        self.assertNotIn('-y',command)
    def test_missing_core_dependency_rejected(self):
        with self.assertRaises(ValueError): self.mod.require_packages([{'file':'docker-ce_1_amd64.deb','architecture':'amd64'}])
    def test_python310_hashing_does_not_require_file_digest(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'data'; path.write_bytes(b'target-python310')
            with patch.object(hashlib,'file_digest',create=True,side_effect=AssertionError('Unavailable on Python 3.10')):
                self.assertEqual(self.mod.sha256_file(path),hashlib.sha256(b'target-python310').hexdigest())
    def test_select_packages_preserves_newer_target_libraries(self):
        from unittest.mock import Mock
        runner=Mock(side_effect=[Mock(stdout='libssl3\n3.0.2-older\n',returncode=0),
                                Mock(stdout='3.0.2-newer',returncode=0),Mock(returncode=0)])
        self.assertEqual(self.mod.select_packages([Path('/bundle/libssl3.deb')],runner),[])
    def test_select_packages_includes_missing_dependencies(self):
        from unittest.mock import Mock
        runner=Mock(side_effect=[Mock(stdout='docker-ce\n29.7.2\n',returncode=0),
                                Mock(stdout='',returncode=1)])
        packages=[Path('/bundle/docker.deb')]
        self.assertEqual(self.mod.select_packages(packages,runner),packages)

if __name__=='__main__': unittest.main()
