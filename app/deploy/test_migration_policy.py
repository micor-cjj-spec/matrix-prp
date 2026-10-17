import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

import migration_policy as policy
from test_approved_controller import preservation


SQL = b'CREATE TABLE prp_future_notes (id BIGINT PRIMARY KEY, user_id BIGINT NOT NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;'
COMMIT = 'a'*40


def contract():
    return {'schema_version':1,'rules':[{'version':22,'file':'V22__future_notes.sql',
        'sha256':hashlib.sha256(SQL).hexdigest(),'mode':'create-empty','tables':['prp_future_notes']}]}


class MigrationPolicyTests(unittest.TestCase):
    def test_new_table_without_controller_allowlist_change(self):
        self.assertEqual(policy.migration_policy_validate(contract(),{22:('V22__future_notes.sql',SQL)}),{22:['prp_future_notes']})

    def test_sql_comments_strings_and_foreign_keys(self):
        sql=b"-- approved new table\nCREATE TABLE `prp_future_notes` (id BIGINT PRIMARY KEY, note VARCHAR(100) DEFAULT 'a;DROP TABLE x;', user_id BIGINT, CONSTRAINT fk_u FOREIGN KEY(user_id) REFERENCES prp_users(id) ON DELETE CASCADE) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;"
        self.assertEqual(policy.migration_policy_sql_tables(sql),['prp_future_notes'])

    def test_unsafe_or_unsupported_sql_rejected(self):
        cases=[SQL+b'DROP TABLE prp_users;', SQL+b'INSERT INTO prp_future_notes VALUES(1,1);',
            SQL.replace(b'CREATE TABLE',b'CREATE TABLE IF NOT EXISTS'),
            SQL.replace(b'ENGINE=InnoDB',b'ENGINE=MyISAM'),
            SQL.replace(b'PRIMARY KEY',b''), SQL.replace(b'prp_future_notes',b'other_schema.prp_future_notes'),
            SQL.replace(b'user_id BIGINT NOT NULL',b'x INT DEFAULT (dangerous_function())'),
            SQL.replace(b'user_id BIGINT NOT NULL',b'x INT CHECK (dangerous_function())'),
            b'/*!50000 DROP TABLE prp_users */'+SQL, SQL[:-1],
            SQL+b'CREATE VIEW prp_view AS SELECT * FROM prp_users;',
            SQL.replace(b'CHARSET=utf8mb4',b"CHARSET=utf8mb4 DATA DIRECTORY='/tmp/x'"),
            SQL.replace(b'CREATE TABLE',b'CREATE TEMPORARY TABLE'),
            SQL.replace(b'user_id BIGINT NOT NULL',b'user_id BIGINT REFERENCES matrix_prp.prp_users(id)')]
        for sql in cases:
            with self.subTest(sql=sql), self.assertRaises(ValueError): policy.migration_policy_sql_tables(sql)

    def test_missing_forged_or_unsupported_contract_rejected(self):
        for mutation in ('digest','table','mode','file','version','extra','missing','duplicate','boolean','commit'):
            data=contract()
            rule=data['rules'][0]
            if mutation=='digest': rule['sha256']='0'*64
            if mutation=='table': rule['tables']=['prp_other']
            if mutation=='mode': rule['mode']='allow-any'
            if mutation=='file': rule['file']='V22__other.sql'
            if mutation=='version': rule['version']=21
            if mutation=='extra': rule['ignore_errors']=True
            if mutation=='missing': data['rules']=[]
            if mutation=='duplicate': data['rules'].append(copy.deepcopy(rule))
            if mutation=='boolean': data['schema_version']=True
            if mutation=='commit': data['commit']='b'*40
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                policy.migration_policy_validate(data,{22:('V22__future_notes.sql',SQL)},COMMIT if mutation=='commit' else None)

    def test_duplicate_json_keys_and_oversized_policy(self):
        for raw in [b'{"schema_version":1,"schema_version":1,"rules":[]}',b' '*262145]:
            with self.assertRaises(ValueError): policy.migration_policy_load(raw)

    def test_real_jar_and_commit_binding_and_pending_versions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with zipfile.ZipFile(root/'backend.jar','w') as jar:
                jar.writestr('BOOT-INF/classes/db/migration/V22__future_notes.sql',SQL)
            data=contract();data['commit']=COMMIT
            raw=json.dumps(data).encode();(root/'migration-policy.json').write_bytes(raw)
            meta={'commit':COMMIT,'schema_version':22,'files':{'migration-policy.json':hashlib.sha256(raw).hexdigest()}}
            self.assertEqual(policy.migration_policy_for_release(root,meta,21),{'prp_future_notes'})
            self.assertEqual(policy.migration_policy_for_release(root,meta,22),set())
            meta['commit']='b'*40
            with self.assertRaises(ValueError): policy.migration_policy_for_release(root,meta,21)
            meta['commit']=COMMIT
            with zipfile.ZipFile(root/'backend.jar','w') as jar:
                jar.writestr('BOOT-INF/classes/db/migration/V22__future_notes.sql',SQL+b'-- changed')
            with self.assertRaises(ValueError): policy.migration_policy_for_release(root,meta,21)

    def test_jar_callback_repeatable_and_nested_sql_are_rejected(self):
        for unexpected in ('beforeMigrate.sql','R__unreviewed.sql','nested/V23__hidden.sql'):
            with self.subTest(path=unexpected),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp)
                with zipfile.ZipFile(root/'backend.jar','w') as jar:
                    jar.writestr('BOOT-INF/classes/db/migration/V22__future_notes.sql',SQL)
                    jar.writestr('BOOT-INF/classes/db/migration/'+unexpected,b'SELECT 1;')
                data=contract();data['commit']=COMMIT;raw=json.dumps(data).encode()
                (root/'migration-policy.json').write_bytes(raw)
                meta={'commit':COMMIT,'schema_version':22,'files':{'migration-policy.json':hashlib.sha256(raw).hexdigest()}}
                with self.assertRaises(ValueError):policy.migration_policy_for_release(root,meta,21)

    def test_no_policy_cannot_authorize_future_migration(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(policy.migration_policy_for_release(Path(tmp),{'schema_version':21},20),set())
            with self.assertRaises(ValueError): policy.migration_policy_for_release(Path(tmp),{'schema_version':22},21)

    def test_runtime_historical_schema_rows_and_empty_table_guards(self):
        check=preservation()
        before={'counts':{'prp_users':1},'row_sha256':{'prp_users':{'1':'original'}},'videos':'owned','table_definitions':{'prp_users':'old-ddl'}}
        after=copy.deepcopy(before)
        after['counts']['prp_future_notes']=0
        after['row_sha256']['prp_future_notes']={}
        after['table_definitions']['prp_future_notes']='new-ddl'
        check(before,after,new_empty_tables={'prp_future_notes'})
        for mutation in ('nonempty','old_row','old_ddl','extra_table','missing_ddl','existing_name'):
            changed=copy.deepcopy(after)
            if mutation=='nonempty': changed['counts']['prp_future_notes']=1
            if mutation=='old_row': changed['row_sha256']['prp_users']['1']='changed'
            if mutation=='old_ddl': changed['table_definitions']['prp_users']='altered'
            if mutation=='extra_table':
                changed['counts']['prp_unreviewed']=0
                changed['row_sha256']['prp_unreviewed']={}
                changed['table_definitions']['prp_unreviewed']='extra'
            if mutation=='missing_ddl': del changed['table_definitions']
            with self.subTest(mutation=mutation), self.assertRaises(AssertionError):
                check(before,changed,new_empty_tables={'prp_users'} if mutation=='existing_name' else {'prp_future_notes'})

    def test_deployed_validator_is_exact_ci_validator(self):
        base=Path(__file__).parent
        source=(base/'approved/prp-release.py').read_text(encoding='utf-8')
        embedded=source.split('# BEGIN VERSIONED MIGRATION POLICY\n')[1].split('\n# END VERSIONED MIGRATION POLICY')[0]
        self.assertEqual(embedded,(base/'migration_policy.py').read_text(encoding='utf-8'))


if __name__=='__main__': unittest.main()
