from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import math
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest

from editing_copilot.history import CancelledOperation, CancellationSupervisor, History


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "state" / "history.sqlite3"
        self.history = History(self.path)

    def tearDown(self):
        self.history.close()
        self.temp.cleanup()

    def test_transaction_lifecycle(self):
        action_id = self.history.record("split_clip", "project-A", {"frame": 10})
        self.assertEqual(self.history.get(action_id)["status"], "proposed")
        self.history.mark(action_id, "pending")
        self.history.mark(action_id, "applied", {"post_hash": "B"})
        verified = self.history.mark(action_id, "verified")
        self.assertEqual(verified["result"], {"post_hash": "B"})
        self.assertEqual(self.history.last_verified("project-A")["id"], action_id)
        self.history.mark(action_id, "undone")
        self.assertIsNone(self.history.last_verified("project-A"))

    def test_persistence_and_recovery(self):
        proposed = self.history.record("split", payload={"label": "Überfahrt"})
        pending = self.history.record("trim", status="pending")
        applied = self.history.record("marker", status="applied")
        verified = self.history.record("guide", status="verified")
        self.history.mark(applied, "applied", {"post_hash": "X"})
        self.history.close()
        self.history = History(self.path)
        self.assertEqual(self.history.get(proposed)["status"], "proposed")
        self.assertEqual(self.history.get(proposed)["payload"], {"label": "Überfahrt"})
        self.assertEqual(self.history.get(pending)["status"], "unknown")
        self.assertEqual(self.history.get(applied)["status"], "unknown")
        self.assertEqual(self.history.get(applied)["result"]["previous_result"], {"post_hash": "X"})
        self.assertEqual(self.history.get(verified)["status"], "verified")

    def test_recovery_not_automatically_replayed(self):
        action_id = self.history.record("split", status="pending")
        self.history.close()
        self.history = History(self.path)
        record = self.history.get(action_id)
        self.history.close()
        self.history = History(self.path)
        self.assertEqual(self.history.get(action_id), record)

    def test_illegal_transition_is_rejected_without_change(self):
        action_id = self.history.record("split")
        for status in ("applied", "verified", "undone"):
            with self.subTest(status=status):
                with self.assertRaisesRegex(ValueError, "transition"):
                    self.history.mark(action_id, status)
                self.assertEqual(self.history.get(action_id)["status"], "proposed")

    def test_applied_cannot_be_cancelled_without_verification(self):
        action_id = self.history.record("trim", status="applied")
        with self.assertRaises(ValueError):
            self.history.mark(action_id, "cancelled")
        self.history.mark(action_id, "unknown")
        self.assertEqual(self.history.get(action_id)["status"], "unknown")

    def test_missing_records(self):
        with self.assertRaises(KeyError):
            self.history.get("missing")
        with self.assertRaises(KeyError):
            self.history.mark("missing", "pending")

    def test_project_filter_and_recent_order(self):
        a = self.history.record("split", "A", status="verified")
        b = self.history.record("guide", "B", status="verified")
        c = self.history.record("marker", "A")
        self.assertEqual([row["id"] for row in self.history.list_recent(2)], [c, b])
        self.assertEqual(self.history.last_verified("A")["id"], a)
        self.assertEqual(self.history.last_verified()["id"], b)
        self.assertIsNone(self.history.last_verified("missing"))

    def test_json_is_isolated_from_caller_mutation(self):
        payload = {"frame": [1]}
        action_id = self.history.record("split", payload=payload)
        payload["frame"].append(2)
        decoded = self.history.get(action_id)
        decoded["payload"]["frame"].append(3)
        self.assertEqual(self.history.get(action_id)["payload"], {"frame": [1]})

    def test_json_validation(self):
        for payload in ({"x": math.nan}, {"x": math.inf}, {"x": object()}):
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    self.history.record("split", payload=payload)
        self.assertEqual(self.history.list_recent(), [])

    def test_sql_strings_are_values(self):
        operation = "'); DROP TABLE actions; --"
        action_id = self.history.record(operation, "A' OR 1=1 --", {"text": operation})
        self.assertEqual(self.history.get(action_id)["operation"], operation)
        self.assertIsNone(self.history.last_verified("A"))

    def test_limits(self):
        for limit in (0, -1, 1001, 1.5, True, "5"):
            with self.subTest(limit=limit):
                with self.assertRaises(ValueError):
                    self.history.list_recent(limit)
        for operation in ("", " ", 123, "x" * 129):
            with self.subTest(operation=operation):
                with self.assertRaises(ValueError):
                    self.history.record(operation)
        with self.assertRaises(ValueError):
            self.history.record("x", status="invented")

    def test_threaded_writes_are_durable(self):
        def write(index):
            action_id = self.history.record("guide", "A", {"index": index})
            self.history.mark(action_id, "pending")
            self.history.mark(action_id, "applied")
            self.history.mark(action_id, "verified")
            return action_id
        with ThreadPoolExecutor(max_workers=8) as pool:
            ids = list(pool.map(write, range(64)))
        self.assertEqual(len(set(ids)), 64)
        self.assertEqual(len(self.history.list_recent(100)), 64)
        self.assertTrue(all(self.history.get(action_id)["status"] == "verified" for action_id in ids))

    def test_closed_history(self):
        self.history.close()
        self.history.close()
        with self.assertRaises(RuntimeError):
            self.history.record("x")

    def test_memory_and_context_manager(self):
        with History(":memory:") as history:
            self.assertIsNone(history.path)
            action_id = history.record("inspect")
            self.assertEqual(history.get(action_id)["operation"], "inspect")

    def test_unknown_schema_fails_without_migration(self):
        self.history.close()
        with closing(sqlite3.connect(self.path)) as connection:
            with connection:
                connection.execute("PRAGMA user_version=99")
        with self.assertRaisesRegex(RuntimeError, "schema version 99"):
            History(self.path)
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 99)


class CancellationTests(unittest.TestCase):
    def test_capture_and_revoke(self):
        supervisor = CancellationSupervisor()
        a, b = supervisor.capture(), supervisor.acquire()
        a.assert_active()
        self.assertIs(a.event, a.cancel_event)
        self.assertEqual(supervisor.stop(), 1)
        self.assertFalse(a.is_active())
        self.assertFalse(b.is_active())
        self.assertTrue(a.event.is_set())
        with self.assertRaises(CancelledOperation):
            a.assert_active()
        supervisor.capture().assert_active()

    def test_queued_old_lease_stays_revoked(self):
        supervisor = CancellationSupervisor()
        queued = supervisor.capture()
        for _ in range(50):
            supervisor.stop()
        self.assertEqual(supervisor.generation, 50)
        self.assertFalse(queued.is_active())
        self.assertTrue(queued.wait(0))

    def test_cross_supervisor_lease_rejected(self):
        a, b = CancellationSupervisor(), CancellationSupervisor()
        self.assertFalse(b.is_active(a.capture()))

    def test_wait_wakes_on_stop(self):
        supervisor = CancellationSupervisor()
        lease = supervisor.capture()
        woke = threading.Event()
        thread = threading.Thread(target=lambda: woke.set() if lease.wait(2) else None)
        thread.start()
        supervisor.stop()
        thread.join(2)
        self.assertTrue(woke.is_set())

    def test_concurrent_cancel_is_monotonic(self):
        supervisor = CancellationSupervisor()
        lease = supervisor.capture()
        with ThreadPoolExecutor(max_workers=8) as pool:
            generations = list(pool.map(lambda _: supervisor.stop(), range(100)))
        self.assertEqual(sorted(generations), list(range(1, 101)))
        self.assertEqual(supervisor.generation, 100)
        self.assertFalse(lease.is_active())


if __name__ == "__main__":
    unittest.main()
