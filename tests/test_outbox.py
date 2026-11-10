"""ทดสอบคิวที่เก็บบนดิสก์และการแยกข้อมูลระหว่างฐานข้อมูล"""
import json
import tempfile
import unittest
from pathlib import Path
from database.outbox import SummaryOutbox
from database.store import Database


class OutboxTests(unittest.TestCase):
    def test_restart_scope_export_and_acknowledgement(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'pending.sqlite3'
            queue = SummaryOutbox(path, 'database-one')
            request_id = queue.enqueue(1, 'a' * 64, 2, 'test', 'ข้อความภาษาไทย')
            restored = SummaryOutbox(path, 'database-one')
            self.assertEqual(restored.items()[0]['request_id'], request_id)
            other = SummaryOutbox(path, 'database-two')
            self.assertEqual(other.items(), [])
            other.acknowledge(request_id)
            self.assertEqual(len(restored.items()), 1)
            export = Path(folder) / 'result.json'
            restored.export(export)
            self.assertEqual(json.loads(export.read_text(encoding='utf-8'))[0]['content'], 'ข้อความภาษาไทย')
            restored.acknowledge(request_id)
            self.assertEqual(queue.items(), [])

    def test_database_scope_does_not_depend_on_password(self):
        first = Database('postgresql://user:secret@localhost:5432/example')
        second = Database('postgresql://user:newsecret@localhost:5432/example')
        other = Database('postgresql://user:secret@localhost:5432/other')
        self.assertEqual(first.scope_key, second.scope_key)
        self.assertNotEqual(first.scope_key, other.scope_key)
        self.assertNotIn('secret', first.scope_key)

    def test_corrupt_queue_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'pending.sqlite3'
            original = b'broken queue'
            path.write_bytes(original)
            with self.assertRaises(Exception):
                SummaryOutbox(path, 'database-one')
            self.assertEqual(path.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
