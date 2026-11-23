import concurrent.futures
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class RevisionTests(unittest.TestCase):
    def modules(self):
        import revision_versions as v
        import revision_ledger as ledger
        return v, ledger

    def policy(self):
        return dict(schema=1, namespace='cloudmeet-v1', server_baseline='11248.0.2',
                    client_baseline='1.0.21', android_base_code=1021,
                    previous_android_code=1021, previous_msi_version='1.0.21', approved=True)

    def request(self, run='100'):
        return dict(repository='stevenzxs/cloudemeet-deploy', workflow='joint', run_id=run,
                    configuration_sha='a' * 40, task='task-1', scope=['server', 'electron', 'android'],
                    sources={'web': 'b' * 40})

    def test_mappings(self):
        v, _ = self.modules()
        for n, code, msi in [(1, 10211, '1.0.22'), (2, 10212, '1.0.23'),
                             (10, 102110, '1.0.31'), (100, 1021100, '1.0.121')]:
            out = v.derive(self.policy(), n)
            self.assertEqual(out['android_code'], code)
            self.assertEqual(out['msi_version'], msi)
            self.assertEqual(out['pe_version'], msi + '.0')
            self.assertEqual(out['client_version'], f'1.0.21+r{n}')
            self.assertEqual(out['server_version'], f'11248.0.2+r{n}')
            self.assertEqual(out['server_tag'], f'11248.0.2-r{n}')

    def test_h5_inherits_existing_parent_revision_without_new_counter(self):
        v, _ = self.modules()
        self.assertEqual(v.derive(self.policy(),15)['revision'],15)
        v.validate_request(dict(self.request(),scope=['server','h5','electron','android']))

    def test_registered_policy_activation_uses_confirmed_baselines(self):
        v, _ = self.modules()
        policy = json.loads((Path(__file__).resolve().parents[2] / 'config/version-policy.json').read_text())
        self.assertIs(policy['approved'], True)
        self.assertEqual(policy['server_baseline'], '11248.0.1')
        self.assertEqual(policy['previous_android_code'], 1021)
        self.assertEqual(policy['previous_msi_version'], '1.0.21')
        out = v.derive(policy, 1)  # Pure preview: does not allocate a revision.
        self.assertEqual(out['server_version'], '11248.0.1+r1')
        self.assertEqual(out['client_version'], '1.0.21+r1')
        self.assertEqual(out['android_code'], 10211)
        self.assertEqual(out['msi_version'], '1.0.22')

    def test_refuses_invalid_overflow_and_unverified_history(self):
        v, _ = self.modules()
        for n in [0, -1, True, '1', 65515, 1000000]:
            with self.assertRaises(ValueError):
                v.derive(self.policy(), n)
        for changes in [dict(previous_android_code=None), dict(approved=False),
                        dict(server_baseline=None), dict(previous_msi_version=None),
                        dict(previous_android_code=10211), dict(previous_msi_version='1.0.22'),
                        dict(android_base_code=3049)]:
            with self.assertRaises(ValueError):
                v.derive(dict(self.policy(), **changes), 1)

    def test_atomic_allocation_retry_binding_and_append_only(self):
        v, ledger = self.modules()
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'ledger.sqlite'
            with self.assertRaises(ValueError):
                ledger.allocate(db, self.policy(), self.request())
            ledger.initialize(db, self.policy())
            first = ledger.allocate(db, self.policy(), self.request())
            self.assertEqual(first, ledger.allocate(db, self.policy(), self.request()))
            self.assertEqual(first['versions']['revision'], 1)
            # No success notification required: a failed/cancelled run consumed r1.
            self.assertEqual(ledger.allocate(db, self.policy(), self.request('101'))['versions']['revision'], 2)
            with self.assertRaises(ValueError):
                ledger.allocate(db, self.policy(), dict(self.request(), configuration_sha='c' * 40))
            v.validate_record(first, self.policy(), 'a' * 40, '100')
            first['versions']['android_code'] = 7
            with self.assertRaises(ValueError):
                v.validate_record(first, self.policy(), 'a' * 40, '100')
            with closing(sqlite3.connect(db)) as con, con:
                with self.assertRaises(sqlite3.DatabaseError):
                    con.execute('DELETE FROM allocations')

    def test_concurrent_allocations_unique_and_missing_db_not_reinitialized(self):
        _, ledger = self.modules()
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'ledger.sqlite'
            ledger.initialize(db, self.policy())
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
                results = list(pool.map(lambda n: ledger.allocate(db, self.policy(), self.request(str(n))), range(1, 13)))
            self.assertEqual(sorted(r['versions']['revision'] for r in results), list(range(1, 13)))
            with self.assertRaises((ValueError, FileExistsError)):
                ledger.initialize(db, self.policy())

    def test_inherited_record_never_creates_allocation_and_attempt_is_retained(self):
        _, ledger = self.modules()
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'ledger.sqlite'
            ledger.initialize(db, self.policy())
            with self.assertRaises(ValueError):
                ledger.allocate(db, self.policy(), self.request(), attempt=1, create=False)
            first = ledger.allocate(db, self.policy(), self.request(), attempt=1)
            self.assertEqual(first, ledger.allocate(db, self.policy(), self.request(), attempt=2, create=False))
            with closing(sqlite3.connect(db)) as con:
                self.assertEqual(con.execute('SELECT run_id,attempt FROM attempts ORDER BY attempt').fetchall(),
                                 [('100', 1), ('100', 2)])

    def test_corrupt_record_and_changed_policy_are_rejected(self):
        _, ledger = self.modules()
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'ledger.sqlite'
            ledger.initialize(db, self.policy())
            ledger.allocate(db, self.policy(), self.request())
            with self.assertRaises(ValueError):
                ledger.allocate(db, dict(self.policy(), namespace='new-baseline'), self.request('101'))
            with closing(sqlite3.connect(db)) as con, con:
                con.execute('DROP TRIGGER allocations_no_update')
                con.execute("UPDATE allocations SET record='{}'")
            with self.assertRaises((ValueError, KeyError)):
                ledger.allocate(db, self.policy(), self.request('101'))


if __name__ == '__main__':
    unittest.main()
