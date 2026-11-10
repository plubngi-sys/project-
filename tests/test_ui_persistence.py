"""ทดสอบหน้าต่างกับฐานข้อมูลจำลอง โดยปล่อยให้ worker และวงจร Qt ทำงานจริง"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pymupdf
from PyQt6.QtWidgets import QApplication, QMessageBox, QFileDialog
from PyQt6.QtTest import QTest
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QCloseEvent
from database.outbox import SummaryOutbox
from project1 import PDFReaderApp


class PersistenceUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def settle(self):
        deadline = time.monotonic() + 4
        while self.window.db_task is not None or self.window.db_queue:
            self.assertLess(time.monotonic(), deadline, 'worker ไม่สิ้นสุดตามเวลาทดสอบ')
            QTest.qWait(10)
        QTest.qWait(20)
        if self.window.db_task is not None:
            self.settle()

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name) / 'sample.pdf'
        doc = pymupdf.open()
        doc.new_page().insert_text((30, 30), 'Page one')
        doc.new_page().insert_text((30, 30), 'Page two')
        doc.save(self.path)
        doc.close()
        self.db = Mock(scope_key='test')
        self.db.register_document.return_value = 12
        self.db.get_document.return_value = {'file_hash': 'a' * 64}
        self.db.get_note.return_value = 'โน้ตเดิม'
        self.db.list_summaries.return_value = []
        self.outbox = SummaryOutbox(Path(self.folder.name) / 'outbox.sqlite3', 'test')
        self.window = PDFReaderApp(self.db, self.outbox)
        self.window.load_pdf(str(self.path))
        self.settle()

    def tearDown(self):
        self.window.db_pool.waitForDone(4000)
        self.app.processEvents()
        self.window.close_document()
        self.window.deleteLater()
        self.folder.cleanup()

    def ai_result(self):
        self.window.ai_context = (12, 'a' * 64, 1, 'test-model')
        self.window.ai_worker = SimpleNamespace(is_cancelled=False, isRunning=lambda: False)
        self.window.on_ai_success('ผลที่ต้องเก็บ')

    def test_search_saved_text_opens_other_document_at_match(self):
        other = Path(self.folder.name) / 'other.pdf'
        other.write_bytes(self.path.read_bytes())
        hit = dict(file_name=other.name, file_path=str(other), document_id=20,
                   page_number=2, kind='ai', excerpt='สรุป JOIN')
        self.db.search_saved_text.return_value = [hit]
        self.window.search_scope.setCurrentIndex(1)
        self.window.txt_search.setText('JOIN')
        self.window.search_text()
        self.settle()
        self.assertIn('ผลสรุป AI', self.window.search_results.item(0).text())
        self.db.register_document.return_value = 20
        self.window.on_search_result_clicked(self.window.search_results.item(0))
        self.settle()
        self.assertEqual((self.window.document_id, self.window.current_page), (20, 1))
        self.assertEqual(self.window.txt_search.text(), 'JOIN')

    def test_save_and_reload(self):
        self.assertEqual(self.window.txt_notes.toPlainText(), 'โน้ตเดิม')
        self.window.txt_notes.setPlainText('โน้ตใหม่')
        self.window.save_current_note()
        self.settle()
        self.db.save_note.assert_called_once_with(12, 1, 'โน้ตใหม่')
        self.window.go_to_page(1)
        self.settle()
        self.db.get_note.assert_called_with(12, 2)
        self.assertEqual(self.window.current_page, 1)

    def test_failed_save_blocks_navigation(self):
        self.window.txt_notes.setPlainText('ห้ามหาย')
        self.window.txt_notes.document().setModified(True)
        self.db.save_note.side_effect = RuntimeError('offline')
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Save), \
             patch.object(QMessageBox, 'warning'):
            self.window.go_to_page(1)
            self.settle()
        self.assertEqual(self.window.current_page, 0)
        self.assertEqual(self.window.spin_page.value(), 1)
        self.assertEqual(self.window.txt_notes.toPlainText(), 'ห้ามหาย')
        self.assertTrue(self.window.txt_notes.document().isModified())

    def test_successful_save_continues_navigation(self):
        self.window.txt_notes.document().setModified(True)
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Save):
            self.window.go_to_page(1)
            self.settle()
        self.assertEqual(self.window.current_page, 1)

    def test_failed_load_keeps_old_document(self):
        old = self.window.doc
        self.db.register_document.side_effect = RuntimeError('offline')
        with patch.object(QMessageBox, 'warning'):
            self.window.load_pdf(str(self.path))
            self.settle()
        self.assertIs(self.window.doc, old)
        self.assertFalse(old.is_closed)

    def test_ai_uses_original_page_and_preserves_note(self):
        self.window.go_to_page(1)
        self.settle()
        self.ai_result()
        self.settle()
        args, kwargs = self.db.add_summary.call_args
        self.assertEqual(args, (12, 1, 'test-model', 'ผลที่ต้องเก็บ'))
        self.assertEqual(kwargs['expected_hash'], 'a' * 64)
        self.assertEqual(self.window.txt_notes.toPlainText(), 'โน้ตเดิม')
        self.assertEqual(self.window.txt_summary.toPlainText(), '')
        self.assertEqual(self.outbox.items(), [])

    def test_failed_summary_survives_restart_and_can_close(self):
        self.db.add_summary.side_effect = RuntimeError('offline')
        with patch.object(QMessageBox, 'warning'):
            self.ai_result()
            self.settle()
        first_id = self.outbox.items()[0]['request_id']
        self.assertIn('ผลที่ต้องเก็บ', self.window.txt_summary.toPlainText())
        event = QCloseEvent()
        self.window.closeEvent(event)
        self.assertTrue(event.isAccepted())
        restored = SummaryOutbox(self.outbox.path, 'test')
        self.assertEqual(restored.items()[0]['request_id'], first_id)
        self.db.add_summary.side_effect = None
        self.window.retry_pending_summaries()
        self.settle()
        self.assertEqual(restored.items(), [])
        self.assertEqual(self.db.add_summary.call_args.kwargs['request_id'], first_id)

    def test_slow_database_does_not_block_gui(self):
        entered, release = threading.Event(), threading.Event()
        worker_threads = []
        def slow(*args):
            worker_threads.append(threading.get_ident())
            entered.set()
            release.wait(2)
        self.db.save_note.side_effect = slow
        pulses = []
        timer = QTimer()
        timer.timeout.connect(lambda: pulses.append(1))
        timer.start(5)
        try:
            self.window.save_current_note()
            QTest.qWait(100)
            self.assertTrue(entered.is_set())
            self.assertGreater(len(pulses), 2)
            self.assertNotEqual(worker_threads[0], threading.get_ident())
            self.assertFalse(self.window.btn_save_note.isEnabled())
        finally:
            release.set()
            self.settle()
            timer.stop()
        self.assertTrue(self.window.btn_save_note.isEnabled())

    def test_cancelled_ai_is_not_saved(self):
        self.window.ai_worker = SimpleNamespace(is_cancelled=True)
        self.window.on_ai_success('ผลที่ยกเลิก')
        self.db.add_summary.assert_not_called()
        self.assertEqual(self.outbox.items(), [])
        self.window.ai_worker = None

    def test_local_write_failure_keeps_result_in_memory(self):
        with patch.object(self.outbox, 'enqueue', side_effect=OSError('disk full')), \
             patch.object(QMessageBox, 'warning'):
            self.ai_result()
        self.assertEqual(len(self.window.volatile_summaries), 1)
        self.db.add_summary.assert_not_called()
        event = QCloseEvent()
        with patch.object(QMessageBox, 'warning'):
            self.window.closeEvent(event)
        self.assertFalse(event.isAccepted())

    def test_export_volatile_result_allows_close(self):
        with patch.object(self.outbox, 'enqueue', side_effect=OSError('disk full')), \
             patch.object(QMessageBox, 'warning'):
            self.ai_result()
        target = str(Path(self.folder.name) / 'export.json')
        with patch.object(QFileDialog, 'getSaveFileName', return_value=(target, 'JSON')):
            self.window.export_pending_summaries()
        self.assertIn('ผลที่ต้องเก็บ', Path(target).read_text(encoding='utf-8'))
        self.assertEqual(self.window.volatile_summaries, [])
        event = QCloseEvent()
        self.window.closeEvent(event)
        self.assertTrue(event.isAccepted())

    def test_commit_then_local_ack_failure_reuses_request_id(self):
        with patch.object(self.outbox, 'acknowledge', side_effect=OSError('disk full')), \
             patch.object(QMessageBox, 'warning'):
            self.ai_result()
            self.settle()
        first_id = self.db.add_summary.call_args.kwargs['request_id']
        self.assertEqual(len(self.outbox.items()), 1)
        self.window.retry_pending_summaries()
        self.settle()
        self.assertEqual(self.db.add_summary.call_args.kwargs['request_id'], first_id)
        self.assertEqual(self.outbox.items(), [])


if __name__ == '__main__':
    unittest.main()
