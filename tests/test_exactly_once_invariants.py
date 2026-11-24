from __future__ import annotations

import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from experiments.exactly_once_lab import crash_probe, handle, initialize


class ExactlyOnceInvariantTests(unittest.TestCase):
    def test_duplicate_delivery_creates_one_effect(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "dedupe.sqlite"
            initialize(db)
            handle(db, "event-1", "immutable", True)
            handle(db, "event-1", "immutable", True)
            with sqlite3.connect(db) as connection:
                effects = connection.execute("SELECT count(*) FROM effects").fetchone()[0]
                dedupe = connection.execute("SELECT count(*) FROM dedupe").fetchone()[0]
            self.assertEqual(effects, 1)
            self.assertEqual(dedupe, 1)

    def test_concurrent_duplicate_deliveries_are_serialized(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "concurrent.sqlite"
            initialize(db)
            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(lambda _: handle(db, "same-event", "same-payload", True), range(32)))
            with sqlite3.connect(db) as connection:
                effects = connection.execute("SELECT count(*) FROM effects").fetchone()[0]
                dedupe = connection.execute("SELECT count(*) FROM dedupe").fetchone()[0]
            self.assertEqual(effects, 1)
            self.assertEqual(dedupe, 1)

    def test_payload_conflict_is_rejected_without_second_effect(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "conflict.sqlite"
            initialize(db)
            handle(db, "stable-id", "original", True)
            with self.assertRaisesRegex(ValueError, "Same id with different payload"):
                handle(db, "stable-id", "altered", True)
            with sqlite3.connect(db) as connection:
                effects = connection.execute("SELECT count(*) FROM effects").fetchone()[0]
            self.assertEqual(effects, 1)

    def test_crash_before_and_after_commit_survive_redelivery(self):
        with tempfile.TemporaryDirectory() as directory:
            result = crash_probe(Path(directory))
        self.assertEqual(result["before"]["exit_code"], 71)
        self.assertEqual(result["before"]["effects_after_crash"], 0)
        self.assertEqual(result["after"]["exit_code"], 72)
        self.assertEqual(result["after"]["effects_after_crash"], 1)
        self.assertEqual(result["before"]["effects_after_redelivery_twice"], 1)
        self.assertEqual(result["after"]["effects_after_redelivery_twice"], 1)
        self.assertEqual(result["before"]["integrity_check"], "ok")
        self.assertEqual(result["after"]["integrity_check"], "ok")


if __name__ == "__main__":
    unittest.main()
