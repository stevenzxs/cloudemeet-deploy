import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class CandidateEvidenceTests(unittest.TestCase):
    def test_source_manifest_covers_seven_pinned_sources(self):
        path = ROOT / 'tools/arm64-candidate-sources.json'
        self.assertTrue(path.exists(), 'Seven-service source manifest is missing')
        data = json.loads(path.read_text())
        self.assertEqual(set(data['services']), {'web', 'app-web', 'api', 'gateway', 'prosody', 'jicofo', 'jvb'})
        for source in data['services'].values():
            self.assertRegex(source['commit'], r'^[0-9a-f]{40}$')
        build = ROOT / 'tools/arm64-candidate-build.py'
        self.assertTrue(build.exists(), 'Native candidate builder is missing')
        text = build.read_text()
        self.assertIn('npm run verify', text)
        self.assertIn('mvn -B -ntp verify', text)
        self.assertIn('go test -race -short', text)
        self.assertNotIn('-DskipTests', text)
        self.assertNotIn("env['VITE_JITSI_SERVER'] =", text)

    def test_candidate_workflow_retains_only_explicit_outputs(self):
        text = (ROOT / '.github/workflows/arm64-smoke.yml').read_text()
        self.assertIn('service: [web, app-web, api, gateway]', text)
        self.assertIn('arm64-candidates/*.tar.gz', text)
        self.assertIn('arm64-candidates/*.json', text)
        self.assertIn('arm64-candidate-evidence.py prosody jicofo jvb', text)
        self.assertNotIn('packages: write', text)
        self.assertNotIn('arm64-evidence/**', text)

    def test_source_checkout_rejects_unexpected_commit(self):
        path = ROOT / 'tools/arm64-candidate-build.py'
        self.assertTrue(path.exists(), 'Native candidate builder is missing')
        spec = importlib.util.spec_from_file_location('candidate_build', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with patch.object(module, 'run'), patch.object(module, 'capture', return_value=b'wrong\n'):
            with self.assertRaisesRegex(RuntimeError, 'Source identity mismatch'):
                module.checkout({'repository': 'https://github.com/example/source.git', 'commit': 'a' * 40}, Path('unused'))

    def test_container_builder_preserves_host_file_ownership_and_has_no_ports(self):
        path = ROOT / 'tools/arm64-candidate-build.py'
        self.assertTrue(path.exists(), 'Native candidate builder is missing')
        spec = importlib.util.spec_from_file_location('candidate_build', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            module.EVIDENCE = Path(directory)
            with patch.object(module.os, 'getuid', return_value=1001, create=True), \
                    patch.object(module.os, 'getgid', return_value=1001, create=True), patch.object(module, 'run') as execute:
                module.container_build('base@sha256:abc', Path(directory), 'npm ci', 'web')
            command = execute.call_args.args[0]
            self.assertIn('1001:1001', command)
            self.assertNotIn('-p', command)
            self.assertNotIn('--privileged', command)

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
            with self.assertRaises(ValueError):
                module.validate_archives([dict(record, archive='../api.tar.gz')], root, {'api'})
            archive.write_bytes(b'changed')
            with self.assertRaises(ValueError):
                module.validate_archives([record], root, {'api'})


if __name__ == '__main__':
    unittest.main()
