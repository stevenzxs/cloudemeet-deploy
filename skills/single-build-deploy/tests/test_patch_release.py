import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))

import patch_release


def policy():
    return dict(schema=1, namespace='cloudmeet-joint-v1', server_baseline='11248.0.2',
                client_baseline='1.0.21', android_base_code=1021, current_revision=47,
                previous_android_code=1021, previous_msi_version='1.0.21', approved=True)


def identities():
    base = {name: 'a' * 40 for name in ('gateway', 'app-web', 'api', 'jitsi-mgr', 'web', 'prosody', 'jicofo', 'jvb')}
    base.update({'electron': 'b' * 40, 'android': 'c' * 40, 'lifecycle': 'd' * 40, 'h5': 'e' * 40})
    return base


def context():
    return dict(repository='stevenzxs/cloudemeet-deploy', workflow='single', run_id='123',
                configuration_sha='f' * 40)


def fake_runner(responses):
    """responses: list of (predicate(argv), CompletedProcess). Records every call."""
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        for predicate, result in responses:
            if predicate(argv):
                return result
        return subprocess.CompletedProcess(argv, 1, '', 'no stubbed response')

    return run, calls


def ok(argv, stdout=''):
    return subprocess.CompletedProcess(argv, 0, stdout, '')


class NextPatchTests(unittest.TestCase):
    PREFIX = 'cloudmeet-11248.0.2-r45-patch.'

    def test_empty_starts_at_one(self):
        self.assertEqual(patch_release.next_patch([], self.PREFIX), 1)

    def test_max_plus_one_and_dirty_tags_skipped(self):
        tags = ['cloudmeet-11248.0.2-r45-patch.1', 'cloudmeet-11248.0.2-r45-patch.3',
                'cloudmeet-11248.0.2-r45-patch.3-extra', 'cloudmeet-11248.0.2-r45-patch.x',
                'cloudmeet-11248.0.2-r4-patch.2', 'unrelated']
        self.assertEqual(patch_release.next_patch(tags, self.PREFIX), 4)

    def test_exhausted_band_raises(self):
        tags = [self.PREFIX + str(n) for n in range(1, 10)]
        with self.assertRaises(ValueError):
            patch_release.next_patch(tags, self.PREFIX)


class RecordTests(unittest.TestCase):
    def test_versions_match_shared_formula_and_record_is_self_checking(self):
        record = patch_release.build_record(policy(), identities(), 45, 'api', context(), patch=1)
        v = record['versions']
        self.assertEqual((v['revision'], v['patch'], v['version_formula']), (45, 1, 2))
        self.assertEqual(v['server_version'], '11248.0.2+r45-patch.1')
        self.assertEqual(v['server_tag'], '11248.0.2-r45-patch.1')
        self.assertEqual(v['client_version'], '1.0.21+r45-patch.1')
        self.assertEqual(v['android_code'], 1021451)
        self.assertEqual(v['msi_version'], '1.0.661')
        self.assertEqual(v['pe_version'], '1.0.661.0')
        self.assertEqual(record['kind'], 'patch')
        self.assertEqual(record['request']['scope'], ['server'])
        self.assertEqual(record['request']['target'], 'api')
        self.assertEqual(record['request']['base_revision'], 45)
        self.assertEqual(record['request']['task'], 'actions-123')
        self.assertEqual(record['request']['sources'], identities())
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'full-build-deploy/tools'))
        from revision_versions import digest
        unsigned = dict(record)
        unsigned.pop('allocation_sha256')
        self.assertEqual(record['allocation_sha256'], digest(unsigned))

    def test_client_target_uses_client_scope(self):
        record = patch_release.build_record(policy(), identities(), 45, 'electron', context(), patch=2)
        self.assertEqual(record['request']['scope'], ['electron'])
        self.assertEqual(record['versions']['android_code'], 1021452)

    def test_rejects_future_base_unknown_target_and_zero(self):
        for base, target in [(48, 'api'), (0, 'api'), (45, 'h5'), (45, 'server')]:
            with self.assertRaises(ValueError, msg=f'{base}/{target}'):
                patch_release.build_record(policy(), identities(), base, target, context(), patch=1)


class CheckBaseTests(unittest.TestCase):
    def releases(self, *tags):
        payload = json.dumps([{'tagName': t, 'isDraft': d} for t, d in tags])
        return lambda argv: argv[:2] == ['gh', 'release'] and 'list' in argv, ok([], payload)

    def assets(self, *names):
        payload = json.dumps({'assets': [{'name': n} for n in names]})
        return lambda argv: argv[:2] == ['gh', 'release'] and 'view' in argv, ok([], payload)

    def test_non_draft_prefix_match_required(self):
        runner, _ = fake_runner([self.releases(('cloudmeet-11248.0.2-r45-9-1', True))])
        with self.assertRaises(ValueError):
            patch_release.check_base(policy(), 45, 'api', runner)
        runner, _ = fake_runner([self.releases(('cloudmeet-11248.0.2-r4-9-1', False))])
        with self.assertRaises(ValueError):
            patch_release.check_base(policy(), 45, 'api', runner)

    def test_server_target_requires_ghcr_digest(self):
        manifest = lambda argv: argv[:2] == ['docker', 'buildx'], ok([], '{"digest": "sha256:' + 'a' * 64 + '"}')
        runner, _ = fake_runner([self.releases(('cloudmeet-11248.0.2-r45-9-1', False)), manifest])
        evidence = patch_release.check_base(policy(), 45, 'api', runner)
        self.assertEqual(evidence['release'], 'cloudmeet-11248.0.2-r45-9-1')
        self.assertTrue(evidence['ghcr_digest'].startswith('sha256:'))
        runner, _ = fake_runner([self.releases(('cloudmeet-11248.0.2-r45-9-1', False))])
        with self.assertRaises(ValueError):
            patch_release.check_base(policy(), 45, 'api', runner)

    def test_client_target_requires_matching_asset(self):
        runner, _ = fake_runner([self.releases(('cloudmeet-11248.0.2-r45-9-1', False)), self.assets('app.msi')])
        evidence = patch_release.check_base(policy(), 45, 'electron', runner)
        self.assertEqual(evidence['asset'], 'app.msi')
        runner, _ = fake_runner([self.releases(('cloudmeet-11248.0.2-r45-9-1', False)), self.assets('app.msi')])
        with self.assertRaises(ValueError):
            patch_release.check_base(policy(), 45, 'android', runner)


class PublishTests(unittest.TestCase):
    def record(self, target):
        return patch_release.build_record(policy(), identities(), 45, target, context(), patch=1)

    def env(self):
        return {'GITHUB_RUN_ID': '123', 'GITHUB_RUN_ATTEMPT': '1', 'GITHUB_SHA': 'f' * 40,
                'GITHUB_REPOSITORY': 'stevenzxs/cloudemeet-deploy', 'TARGET_ARCH': 'amd64'}

    def test_jitsi_mgr_publishes_artifacts_without_image_push(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'artifacts').mkdir()
            (root / 'artifacts' / 'jitsi-mgr.jar').write_bytes(b'jar-bytes')
            evidence = {'service': 'jitsi-mgr', 'batch': '11248.0.2-r45-patch.1-123-1', 'version': '11248.0.2+r45-patch.1',
                        'run_id': '123', 'attempt': '1', 'deployment_commit': 'f' * 40,
                        'architecture': 'amd64', 'source_commit': 'a' * 40,
                        'version_assignment': self.record('jitsi-mgr'),
                        'files': {'jitsi-mgr.jar': 'x' * 64}}
            (root / 'build-evidence.json').write_text(json.dumps(evidence))
            runner, calls = fake_runner([(lambda argv: argv[:2] == ['gh', 'release'], ok([], '{}'))])
            patch_release.publish('jitsi-mgr', root, self.record('jitsi-mgr'), policy(), runner, self.env())
            pushed = [c for c in calls if 'push' in c]
            self.assertEqual(pushed, [])
            created = [c for c in calls if c[:2] == ['gh', 'release'] and 'create' in c]
            self.assertTrue(created and 'cloudmeet-11248.0.2-r45-patch.1' in created[0])

    def test_server_publish_requires_absent_tag_before_push(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / 'api.tar.gz'
            archive.write_bytes(b'image-bytes')
            import hashlib
            sha = hashlib.sha256(b'image-bytes').hexdigest()
            record = self.record('api')
            build = {'service': 'api', 'batch': '11248.0.2-r45-patch.1-123-1', 'version': '11248.0.2+r45-patch.1',
                     'run_id': '123', 'attempt': '1', 'deployment_commit': 'f' * 40, 'workflow_commit': 'f' * 40,
                     'platform': 'linux/amd64', 'archive': 'api.tar.gz', 'bytes': len(b'image-bytes'), 'sha256': sha,
                     'tag': 'cloudmeet/api:11248.0.2-r45-patch.1-123-1', 'image_id': 'sha256:' + 'b' * 64,
                     'source': {'commit': 'a' * 40}, 'source_dirty': False, 'version_assignment': record}
            (root / 'api.json').write_text(json.dumps(build))
            image = json.dumps([{'Id': 'sha256:' + 'b' * 64, 'Os': 'linux', 'Architecture': 'amd64',
                                 'Config': {'Labels': {'org.opencontainers.image.revision': 'a' * 40,
                                                       'io.cloudmeet.batch': '11248.0.2-r45-patch.1-123-1'}}}])
            runner, calls = fake_runner([
                (lambda argv: argv[:2] == ['docker', 'manifest'], subprocess.CompletedProcess([], 1, '', 'manifest unknown')),
                (lambda argv: argv[:3] == ['docker', 'image', 'inspect'], ok([], image)),
                (lambda argv: argv[:2] == ['docker', 'buildx'], ok([], '{"digest": "sha256:' + 'b' * 64 + '"}')),
                (lambda argv: argv[0] == 'docker', ok([], '{}')),
                (lambda argv: argv[:2] == ['gh', 'release'], ok([], '{}')),
            ])
            patch_release.publish('api', root, record, policy(), runner, self.env())
            verbs = [' '.join(c[:3]) for c in calls]
            absent = next(i for i, c in enumerate(calls) if c[:2] == ['docker', 'manifest'])
            push = next(i for i, c in enumerate(calls) if c[:2] == ['docker', 'push'])
            self.assertLess(absent, push)
            self.assertIn('ghcr.io/stevenzxs/cloudmeet-api:11248.0.2-r45-patch.1', calls[push])
            self.assertTrue(any('create' in c for c in calls if c[:2] == ['gh', 'release']))

    def test_existing_registry_tag_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'api.tar.gz').write_bytes(b'image-bytes')
            import hashlib
            sha = hashlib.sha256(b'image-bytes').hexdigest()
            record = self.record('api')
            build = {'service': 'api', 'batch': '11248.0.2-r45-patch.1-123-1', 'version': '11248.0.2+r45-patch.1',
                     'run_id': '123', 'attempt': '1', 'deployment_commit': 'f' * 40, 'workflow_commit': 'f' * 40,
                     'platform': 'linux/amd64', 'archive': 'api.tar.gz', 'bytes': len(b'image-bytes'), 'sha256': sha,
                     'tag': 'cloudmeet/api:11248.0.2-r45-patch.1-123-1', 'image_id': 'sha256:' + 'b' * 64,
                     'source': {'commit': 'a' * 40}, 'source_dirty': False, 'version_assignment': record}
            (root / 'api.json').write_text(json.dumps(build))
            runner, calls = fake_runner([
                (lambda argv: argv[:2] == ['docker', 'manifest'], ok([], '{}')),
                (lambda argv: argv[0] == 'docker', ok([], '{}')),
            ])
            with self.assertRaises(ValueError):
                patch_release.publish('api', root, record, policy(), runner, self.env())
            self.assertEqual([c for c in calls if c[:2] == ['docker', 'push']], [])


if __name__ == '__main__':
    unittest.main()
