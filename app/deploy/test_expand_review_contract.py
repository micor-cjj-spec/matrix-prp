"""ENG-03B reviewer evidence must not grant permission or conceal old-data drift."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO

from expand_review_contract import (
    create_review_contract, verify_review_contract, load_json, main, sha, canonical
)

SQL = (b"ALTER TABLE prp_expand_fixture ADD COLUMN source_platform VARCHAR(32) NULL, "
       b"ALGORITHM=INSTANT;")
COMMIT = "a" * 40
HASH = sha(b"fixture")


def snapshot():
    return {
        "table": "prp_expand_fixture",
        "mysql_version": "8.4.11",
        "schema_version": 23,
        "source_commit": COMMIT,
        "columns": [
            {"name": "id", "type": "bigint", "nullable": False, "default": None,
             "extra": "", "ordinal": 1},
            {"name": "owner_user_id", "type": "bigint", "nullable": False,
             "default": None, "extra": "", "ordinal": 2},
            {"name": "note", "type": "varchar(30)", "nullable": False,
             "default": None, "extra": "", "ordinal": 3},
        ],
        "row_count": 2,
        "old_rows_sha256": sha(b"1,101,alpha\n2,102,beta"),
        "indexes_sha256": HASH,
        "constraints_sha256": HASH,
        "triggers_sha256": HASH,
        "added_column_nonnull_count": None,
    }


def valid_triplet():
    before = snapshot()
    after = copy.deepcopy(before)
    after["columns"].append({
        "name": "source_platform", "type": "varchar(32)", "nullable": True,
        "default": None, "extra": "", "ordinal": 4,
    })
    after["added_column_nonnull_count"] = 0
    contract = create_review_contract(
        SQL, before, source_commit=COMMIT, target_schema_version=24)
    return contract, before, after


class ExpandReviewContractTests(unittest.TestCase):
    def test_valid_rehearsal_is_review_ready_but_never_production_approved(self):
        contract, before, after = valid_triplet()
        self.assertFalse(contract["production_authorized"])
        self.assertTrue(contract["controller_upgrade_required"])
        self.assertEqual(contract["target_schema_version"], 24)
        result = verify_review_contract(contract, SQL, before, after)
        self.assertEqual(result["classification"], "READY_FOR_SPECIALIST_REVIEW")
        self.assertFalse(result["production_authorized"])
        self.assertEqual(result["row_count_preserved"], 2)

    def test_contract_mutations_rejected(self):
        changes = {
            "production_authorized": True,
            "controller_upgrade_required": False,
            "status": "APPROVED",
            "mode": "allow-any",
            "rollback_strategy": "restore-prod-db",
            "mysql_family": "8.0",
            "source_commit": "b" * 40,
            "table": "prp_other",
            "column": "other",
            "column_type": "BIGINT",
            "sql_sha256": "0" * 64,
            "old_rows_sha256": "0" * 64,
            "old_columns_sha256": "0" * 64,
            "old_indexes_sha256": "0" * 64,
            "old_constraints_sha256": "0" * 64,
            "old_triggers_sha256": "0" * 64,
            "base_schema_version": 22,
            "target_schema_version": 26,
            "schema_version": True,
        }
        for key, value in changes.items():
            with self.subTest(key=key):
                contract, before, after = valid_triplet()
                contract[key] = value
                with self.assertRaises(ValueError):
                    verify_review_contract(contract, SQL, before, after)
        for key in ("production_authorized", "rollback_strategy", "sql_sha256"):
            contract, before, after = valid_triplet()
            del contract[key]
            with self.subTest(missing=key), self.assertRaises(ValueError):
                verify_review_contract(contract, SQL, before, after)
        contract, before, after = valid_triplet()
        contract["ignore_failures"] = True
        with self.assertRaises(ValueError):
            verify_review_contract(contract, SQL, before, after)

    def test_rehearsal_drift_and_missing_evidence_rejected(self):
        mutations = [
            lambda a: a.update(row_count=3),
            lambda a: a.update(old_rows_sha256="0" * 64),
            lambda a: a.update(indexes_sha256="0" * 64),
            lambda a: a.update(constraints_sha256="0" * 64),
            lambda a: a.update(triggers_sha256="0" * 64),
            lambda a: a.update(mysql_version="8.4.12"),
            lambda a: a.update(source_commit="b" * 40),
            lambda a: a.update(schema_version=24),
            lambda a: a.update(table="prp_other"),
            lambda a: a.update(added_column_nonnull_count=1),
            lambda a: a["columns"][0].update(nullable=True),
            lambda a: a["columns"][1].update(default="100"),
            lambda a: a["columns"][-1].update(type="varchar(64)"),
            lambda a: a["columns"][-1].update(nullable=False),
            lambda a: a["columns"][-1].update(default=""),
            lambda a: a["columns"][-1].update(extra="auto_increment"),
            lambda a: a["columns"][-1].update(ordinal=5),
            lambda a: a["columns"].insert(0, a["columns"].pop()),
            lambda a: a["columns"].append(copy.deepcopy(a["columns"][-1])),
            lambda a: a.pop("constraints_sha256"),
        ]
        for index, mutation in enumerate(mutations):
            contract, before, after = valid_triplet()
            mutation(after)
            with self.subTest(index=index), self.assertRaises((ValueError, KeyError)):
                verify_review_contract(contract, SQL, before, after)

    def test_untrustworthy_old_evidence_rejected(self):
        mutations = [
            lambda b: b.update(added_column_nonnull_count=0),
            lambda b: b["columns"][-1].update(name="source_platform"),
            lambda b: b.update(table="prp_other"),
            lambda b: b.update(source_commit="b" * 40),
            lambda b: b.update(mysql_version="8.0.42"),
            lambda b: b.update(row_count=True),
            lambda b: b["columns"][1].update(nullable=1),
            lambda b: b["columns"][1].update(ordinal=True),
            lambda b: b["columns"][0].update(name="Owner_User"),
        ]
        for index, mutation in enumerate(mutations):
            before = snapshot()
            mutation(before)
            with self.subTest(index=index), self.assertRaises(ValueError):
                create_review_contract(SQL, before, source_commit=COMMIT, target_schema_version=24)

    def test_malformed_json_and_forged_ddl_rejected(self):
        for raw in [b'{"a":1,"a":2}', b"{" + b" " * 17000 + b"}", b'[]' * 9000,
                    b"{", b""]:
            with self.subTest(raw=raw[:20]), self.assertRaises(ValueError):
                load_json(raw)
        contract, before, after = valid_triplet()
        with self.assertRaises(ValueError):
            verify_review_contract(
                contract, SQL.replace(b"ALGORITHM=INSTANT", b"ALGORITHM=COPY"),
                before, after)
        with self.assertRaises(ValueError):
            verify_review_contract(contract, SQL + b" DROP TABLE prp_users;", before, after)

    def test_cli_outputs_only_review_status_and_uses_fail_closed_exit(self):
        contract, before, after = valid_triplet()
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / "candidate.sql").write_bytes(SQL)
            for name, data in (("contract", contract), ("before", before), ("after", after)):
                (folder / (name + ".json")).write_bytes(canonical(data))
            args = sum(([f"--{name}", str(folder / (name + ext))]
                        for name, ext in (("sql", ".sql"), ("contract", ".json"),
                                          ("before", ".json"), ("after", ".json"))), [])
            with redirect_stdout(StringIO()) as output:
                self.assertEqual(main(args), 0)
            self.assertFalse(json.loads(output.getvalue())["production_authorized"])
            (folder / "after.json").write_text('{"row_count":0}')
            with self.assertRaises(SystemExit) as failure:
                main(args)
            self.assertEqual(failure.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
