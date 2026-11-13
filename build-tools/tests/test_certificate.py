"""No Docker or server: target-side certificate input boundaries."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('certificate',Path(__file__).parents[1]/'offline-runtime/certificate.py')
certificate=importlib.util.module_from_spec(spec);spec.loader.exec_module(certificate)


class CertificateTests(unittest.TestCase):
    def test_explicit_origin_only(self):
        self.assertEqual(certificate.origin_host('https://115.190.243.21:8443'),'115.190.243.21')
        for value in ('http://host','https://host/','https://u:p@host','https://host?q=x','https://host:99999'):
            with self.assertRaises(ValueError): certificate.origin_host(value)

    def test_reject_traversal_and_private_ca(self):
        import tarfile
        import io
        for name in ('../server.key','cert/ca.key','/cert/server.key'):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                archive=Path(tmp)/'cert.tar.gz'
                with tarfile.open(archive,'w:gz') as tar:
                    info=tarfile.TarInfo(name);info.size=1;tar.addfile(info,io.BytesIO(b'x'))
                with self.assertRaises(ValueError): certificate.unpack_certificate(archive,Path(tmp)/'out')

    def test_real_local_bundle_inventory_only(self):
        archive=Path(__file__).parents[2]/'cert/cert.tar.gz'
        if not archive.exists(): self.skipTest('Private target input deliberately absent on Actions')
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'cert';certificate.unpack_certificate(archive,out)
            self.assertTrue((out/'server.key').is_file())
            self.assertFalse((out/'ca.key').exists())

    def test_setup_safe_extract_and_existing_directory_refusal(self):
        import hashlib
        import io
        import tarfile
        spec=importlib.util.spec_from_file_location('setup',Path(__file__).parents[1]/'setup.py')
        setup=importlib.util.module_from_spec(spec);spec.loader.exec_module(setup)
        with tempfile.TemporaryDirectory() as tmp:
            archive=Path(tmp)/'server.tar.gz'
            with tarfile.open(archive,'w:gz') as tar:
                info=tarfile.TarInfo('server/deploy.py');info.size=1
                tar.addfile(info,io.BytesIO(b'x'))
            Path(str(archive)+'.sha256').write_text(hashlib.sha256(archive.read_bytes()).hexdigest()+'  server.tar.gz\n')
            self.assertEqual((setup.extract_server(archive)/'deploy.py').read_bytes(),b'x')
            with self.assertRaises(FileExistsError): setup.extract_server(archive)
            Path(str(archive)+'.sha256').write_text('0'*64+'  server.tar.gz\n')
            with self.assertRaises(ValueError): setup.extract_server(archive)
