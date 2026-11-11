import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CandidateEvidenceTests(unittest.TestCase):
    def load_module(self):
        path = ROOT / 'tools/arm64-candidate-evidence.py'
        self.assertTrue(path.exists(), 'Candidate evidence validator is missing')
        spec = importlib.util.spec_from_file_location('candidate_evidence', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_validate_rejects_wrong_platform_and_unpinned_source(self):
        module = self.load_module()
        source = {'commit': 'a' * 40, 'repository': 'https://github.com/example/source.git'}
        image = {'Os': 'linux', 'Architecture': 'arm64', 'Id': 'sha256:' + 'b' * 64}
        module.validate_identity(image, source)
        for field, value in [('Architecture', 'amd64'), ('Os', 'windows')]:
            with self.assertRaises(ValueError):
                module.validate_identity(dict(image, **{field: value}), source)
        with self.assertRaises(ValueError):
            module.validate_identity(image, dict(source, commit='main'))

    def test_archive_validation_rejects_tamper_and_missing_services(self):
        module = self.load_module()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / 'api.tar.gz'
            archive.write_bytes(b'candidate')
            record = {'service': 'api', 'archive': archive.name, 'size': archive.stat().st_size,
                      'sha256': hashlib.sha256(archive.read_bytes()).hexdigest()}
            module.validate_archives([record], root, {'api'})
            with self.assertRaises(ValueError):
                module.validate_archives([record], root, {'api', 'web'})
            with self.assertRaises(ValueError):
                module.validate_archives([record, record], root, {'api'})
            archive.write_bytes(b'changed')
            with self.assertRaises(ValueError):
                module.validate_archives([record], root, {'api'})


if __name__ == '__main__':
    unittest.main()
