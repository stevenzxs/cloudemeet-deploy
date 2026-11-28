import json
import base64
from pathlib import Path
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))

import clean

FAKE_KEY = base64.b64encode(b'host-key-bytes-for-test').decode()


def fake_runner(responses):
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


def container(project, service, working_dir):
    return json.dumps({'ID': 'c1' + service, 'Names': 'n-' + service,
                       'Labels': 'com.docker.compose.project=' + project +
                                 ',com.docker.compose.service=' + service +
                                 ',com.docker.compose.project.working_dir=' + working_dir})


class JdbcTests(unittest.TestCase):
    def test_postgres_url_parsed_and_h2_is_local_only(self):
        self.assertEqual(clean.parse_jdbc('jdbc:postgresql://db.internal:5433/jitsi_mgr'), ('db.internal', 5433, 'jitsi_mgr'))
        self.assertEqual(clean.parse_jdbc('jdbc:postgresql://db/jitsi_mgr?ssl=false'), ('db', 5432, 'jitsi_mgr'))
        self.assertEqual(clean.parse_jdbc('jdbc:h2:file:/app/data/jitsi-mgr'), None)

    def test_non_jitsi_database_name_refused(self):
        with self.assertRaises(ValueError):
            clean.parse_jdbc('jdbc:postgresql://db/customers')
        with self.assertRaises(ValueError):
            clean.parse_jdbc('jdbc:mysql://db/jitsi_mgr')


class RootGuardTests(unittest.TestCase):
    def test_dangerous_roots_refused(self):
        for root in ['/', '/root', '/home', '/etc', 'relative/path', '/opt/x/..']:
            with self.assertRaises(ValueError, msg=root):
                clean.validate_instance_root(root)
        self.assertEqual(clean.validate_instance_root('/srv/cloudmeet/prod'), '/srv/cloudmeet/prod')

    def test_marker_requirement(self):
        probe = lambda command: ok([], 'present:candidate.json\npresent:data\n')
        clean.require_instance_markers('/srv/cloudmeet/prod', probe)
        probe = lambda command: ok([], 'present:data\n')
        with self.assertRaises(ValueError):
            clean.require_instance_markers('/srv/cloudmeet/prod', probe)


class InventoryTests(unittest.TestCase):
    def test_containers_grouped_by_project_and_foreign_excluded(self):
        lines = '\n'.join([
            container('cloudmeet-11248-0-1-r45-1', 'gateway', '/srv/cm/prod'),
            container('cloudmeet-11248-0-1-r45-1', 'jvb', '/srv/cm/prod'),
            container('other-project', 'app', '/srv/other'),
        ]) + '\n'
        inventory = clean.group_containers(lines)
        self.assertEqual(set(inventory), {'cloudmeet-11248-0-1-r45-1', 'other-project'})
        self.assertEqual(len(inventory['cloudmeet-11248-0-1-r45-1']), 2)

    def test_ambiguous_multiple_cloudmeet_projects_refused(self):
        lines = '\n'.join([
            container('cloudmeet-a', 'gateway', '/srv/cm/a'),
            container('cloudmeet-b', 'gateway', '/srv/cm/b'),
        ]) + '\n'
        with self.assertRaises(ValueError):
            clean.select_project(lines, '/srv/cm/a')

    def test_project_selected_by_instance_working_dir(self):
        lines = '\n'.join([
            container('cloudmeet-a', 'gateway', '/srv/cm/a'),
            container('other', 'app', '/srv/other'),
        ]) + '\n'
        self.assertEqual(clean.select_project(lines, '/srv/cm/a'), 'cloudmeet-a')

    def test_plain_cloudmeet_project_matches(self):
        # Live instance on 118.193.36.35 uses the plain project name "cloudmeet".
        lines = '\n'.join([
            container('cloudmeet', 'prosody', '/opt/cloudmeet'),
            container('cloudmeet', 'api', '/opt/cloudmeet'),
        ]) + '\n'
        self.assertEqual(clean.select_project(lines, '/opt/cloudmeet'), 'cloudmeet')


class ApplySafetyTests(unittest.TestCase):
    def test_no_global_prune_or_unguarded_rm(self):
        commands = clean.apply_commands(
            project='cloudmeet-a', root='/srv/cm/prod',
            postgres=('db', 5432, 'jitsi_mgr'), db_user='mgr', db_password='secret')
        joined = '\n'.join(commands)
        self.assertNotIn('prune', joined)
        self.assertNotIn('rm -rf / ', joined)
        for command in commands:
            if 'rm -rf' in command:
                self.assertIn('/srv/cm/prod', command)
            if 'volume rm' in command:
                self.assertIn('label=com.docker.compose.project=cloudmeet-a', command)
        self.assertIn('DROP SCHEMA public CASCADE', joined)
        self.assertIn('CREATE SCHEMA public', joined)

    def test_apply_without_postgres_skips_db_step(self):
        commands = clean.apply_commands(project='cloudmeet-a', root='/srv/cm/prod',
                                        postgres=None, db_user='', db_password='')
        self.assertNotIn('DROP SCHEMA', '\n'.join(commands))

    def test_untagged_container_images_removed_and_verified(self):
        commands = clean.apply_commands(project='cloudmeet', root='/opt/cloudmeet',
                                        postgres=None, db_user='', db_password='',
                                        image_ids=('1555e62283d1', '587f052853ff'))
        joined = '\n'.join(commands)
        self.assertIn('docker rmi 1555e62283d1 587f052853ff', joined)
        verify = '\n'.join(clean.verify_commands('cloudmeet', '/opt/cloudmeet',
                                                 ('1555e62283d1', '587f052853ff')))
        self.assertIn('docker images -q 1555e62283d1', verify)
        self.assertIn('docker images -q 587f052853ff', verify)


class FingerprintTests(unittest.TestCase):
    def test_first_contact_requires_explicit_acceptance(self):
        scan = '10.0.0.1 ssh-ed25519 ' + FAKE_KEY + '\n'
        with self.assertRaises(ValueError):
            clean.check_fingerprint('10.0.0.1', 22, None, scan)
        clean.check_fingerprint('10.0.0.1', 22, clean.host_fingerprint(scan), scan)

    def test_fingerprint_mismatch_refused(self):
        scan = '10.0.0.1 ssh-ed25519 ' + FAKE_KEY + '\n'
        with self.assertRaises(ValueError):
            clean.check_fingerprint('10.0.0.1', 22, 'SHA256:wrongwrong', scan)

    def test_accepted_may_match_any_scanned_key(self):
        # ssh-keyscan line ordering is unstable; accepting the rsa key must not
        # be rejected just because ed25519 sorts first (118.193.36.35).
        rsa_key = 'AAAA'
        scan = '10.0.0.1 ssh-ed25519 ' + FAKE_KEY + '\n10.0.0.1 ssh-rsa ' + rsa_key + '\n'
        import base64, hashlib
        rsa_fp = 'SHA256:' + base64.b64encode(hashlib.sha256(base64.b64decode(rsa_key)).digest()).decode().rstrip('=')
        self.assertEqual(clean.check_fingerprint('10.0.0.1', 22, rsa_fp, scan), rsa_fp)


class FlowTests(unittest.TestCase):
    def dispatch(self):
        keyscan = '1.2.3.4 ssh-ed25519 ' + FAKE_KEY + '\n'
        ps_lines = (container('cloudmeet-a', 'gateway', '/srv/cm/prod') + '\n'
                    + container('cloudmeet-a', 'jvb', '/srv/cm/prod') + '\n')
        images = json.dumps({'Repository': 'cloudmeet/api', 'Tag': 'b1', 'ID': 'img1'}) + '\n' \
            + json.dumps({'Repository': 'other/img', 'Tag': 'x', 'ID': 'img2'}) + '\n'

        def run(argv, **kwargs):
            s = ' '.join(map(str, argv))
            if argv[0] == 'ssh-keyscan':
                return ok([], keyscan)
            if 'for f in' in s:
                return ok([], 'present:candidate.json\npresent:data\npresent:.env\n')
            if s.endswith('hostname'):
                return ok([], 'target-host\n')
            if 'docker ps -a' in s:
                return ok([], ps_lines)
            if 'docker volume ls' in s:
                return ok([], 'cloudmeet-a_caddy_data\ncloudmeet-a_caddy_config\n')
            if 'docker images --format' in s:
                return ok([], images)
            if 'jitsi-mgr.env' in s:
                return ok([], 'JITSI_MGR_DB_URL=jdbc:postgresql://db:5432/jitsi_mgr\nJITSI_MGR_DB_USER=mgr\n')
            if 'JITSI_MGR_DB_PASSWORD' in s:
                return ok([], 'JITSI_MGR_DB_PASSWORD=secret\n')
            return ok([], '')

        calls = []
        def tracked(argv, **kwargs):
            calls.append(' '.join(map(str, argv)))
            return run(argv, **kwargs)
        return tracked, calls

    def args(self, *extra):
        return ['--host', '1.2.3.4', '--instance-root', '/srv/cm/prod',
                '--accept-fingerprint', clean.host_fingerprint('1.2.3.4 ssh-ed25519 ' + FAKE_KEY + '\n'),
                *extra]

    def test_inventory_reports_project_images_volumes_and_postgres(self):
        runner, _ = self.dispatch()
        import io, contextlib
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            clean.main(self.args(), runner=runner)
        report = json.loads(out.getvalue())
        self.assertEqual(report['project'], 'cloudmeet-a')
        self.assertEqual(len(report['containers']), 2)
        self.assertEqual(sorted(report['volumes']), ['cloudmeet-a_caddy_config', 'cloudmeet-a_caddy_data'])
        self.assertEqual(len(report['images']), 1)
        self.assertEqual(report['postgres'], ['db', 5432, 'jitsi_mgr'])
        self.assertNotIn('apply', report)

    def test_local_mode_skips_ssh_and_keyscan(self):
        runner, calls = self.dispatch()
        import io, contextlib
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            clean.main(['--local', '--instance-root', '/srv/cm/prod'], runner=runner)
        report = json.loads(out.getvalue())
        self.assertEqual(report['project'], 'cloudmeet-a')
        self.assertFalse(any('ssh-keyscan' in c or c.startswith('ssh ') for c in calls))
        self.assertTrue(all(c.startswith('bash -c') for c in calls))

    def test_remote_mode_uses_ssh_and_keyscan(self):
        runner, calls = self.dispatch()
        import io, contextlib
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            clean.main(self.args('--remote'), runner=runner)
        self.assertTrue(any(c.startswith('ssh-keyscan') for c in calls))
        self.assertTrue(any(c.startswith('ssh ') for c in calls))

    def test_apply_executes_wipe_and_verifies_zero_residue(self):
        runner, calls = self.dispatch()
        import io, contextlib
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            clean.main(self.args('--apply'), runner=runner)
        text = out.getvalue()
        self.assertIn('READY_FOR_REINSTALL', text)
        destructive = [c for c in calls if any(k in c for k in ('docker rm', 'volume rm', 'network rm', 'docker rmi', 'rm -rf', 'psql'))]
        self.assertGreaterEqual(len(destructive), 5)
        joined = '\n'.join(destructive)
        self.assertIn('DROP SCHEMA public CASCADE', joined)
        self.assertNotIn('prune', joined)


if __name__ == '__main__':
    unittest.main()
