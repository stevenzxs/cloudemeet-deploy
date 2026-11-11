import importlib.util
import json
from pathlib import Path
import unittest
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class StackTests(unittest.TestCase):
    def load(self):
        path = ROOT / 'tools/arm64-stack.py'
        self.assertTrue(path.exists(), 'Seven-service integration script missing')
        spec = importlib.util.spec_from_file_location('stack', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_gate_requires_exact_seven_healthy_identities(self):
        m = self.load()
        images = {s: 'sha256:' + str(i) * 64 for i, s in enumerate(m.SERVICES)}
        states = [{'service': s, 'image': i, 'running': True, 'oom': False, 'restarts': 0}
                  for s, i in images.items()]
        self.assertTrue(m.accepts(states, images, 1))
        self.assertFalse(m.accepts(states[:-1], images, 1))
        self.assertFalse(m.accepts(states, images, 0))
        self.assertFalse(m.accepts(states + [states[0]], images, 1))
        for key, value in [('oom', True), ('running', False), ('restarts', 1), ('image', 'wrong')]:
            self.assertFalse(m.accepts([dict(states[0], **{key: value})] + states[1:], images, 1))

    def test_topology_has_no_pulls_host_ports_or_source_mounts(self):
        m = self.load()
        images = {s: 'sha256:' + str(i) * 64 for i, s in enumerate(m.SERVICES)}
        config = m.topology(images, Path('private').resolve(), {'focus': 'secret1', 'jvb': 'secret2', 'jwt': 'secret3'})
        self.assertEqual(set(config['services']), set(images))
        self.assertTrue(config['networks']['test']['internal'])
        for name, service in config['services'].items():
            self.assertEqual(service['image'], images[name])
            self.assertEqual(service['pull_policy'], 'never')
            self.assertNotIn('ports', service)
            self.assertNotIn('build', service)
        self.assertNotIn('app.jar', json.dumps(config))

    def test_websocket_accept_is_validated(self):
        m = self.load()
        valid = b'HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=\r\nSec-WebSocket-Protocol: xmpp\r\n\r\n'
        self.assertTrue(m.valid_upgrade(valid))
        self.assertFalse(m.valid_upgrade(valid.replace(b'101', b'200')))
        self.assertFalse(m.valid_upgrade(valid.replace(b's3pPLMB', b'invalid')))

    def test_locked_sources_and_exact_five_artifacts(self):
        lock = json.loads((ROOT / 'tools/arm64-stack-lock.json').read_text())
        sources = json.loads((ROOT / 'tools/arm64-candidate-sources.json').read_text())['services']
        self.assertEqual(set(lock['images']), set(sources))
        self.assertEqual(len({a['id'] for a in lock['artifacts']}), 5)
        self.assertEqual((lock['run'], lock['attempt']), (42967794060, 2))
        for name, image in lock['images'].items():
            self.assertEqual(image['source'], sources[name])

    def test_import_rejects_untrusted_artifact_before_docker_load(self):
        m = self.load()
        with tempfile.TemporaryDirectory() as directory:
            def download(identity, path):
                path.write_bytes(b'tampered')
            with patch.object(m, 'download', side_effect=download), patch.object(m, 'run') as docker:
                with self.assertRaisesRegex(RuntimeError, 'Artifact digest mismatch'):
                    m.import_images(Path(directory), {'artifacts': [{'id': 1, 'digest': 'sha256:wrong'}]})
                docker.assert_not_called()


if __name__ == '__main__':
    unittest.main()
