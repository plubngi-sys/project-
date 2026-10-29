"""ทดสอบการเชื่อมหน้าต่างกับโมดูลจัดเก็บ โดยไม่ต้องเรียก AI หรือฐานข้อมูลจริง"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pymupdf
from PyQt6.QtWidgets import QApplication, QMessageBox
from project1 import PDFReaderApp


class PersistenceUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name) / 'sample.pdf'
        doc = pymupdf.open()
        doc.new_page().insert_text((30, 30), 'Page one')
        doc.new_page().insert_text((30, 30), 'Page two')
        doc.save(self.path)
        doc.close()
        self.db = Mock()
        self.db.register_document.return_value = 12
        self.db.get_note.return_value = 'โน้ตเดิม'
        self.db.list_summaries.return_value = []
        self.window = PDFReaderApp(self.db)
        self.window.load_pdf(str(self.path))

    def tearDown(self):
        if self.window.doc:
            self.window.doc.close()
        self.window.deleteLater()
        self.folder.cleanup()

    def test_save_and_reload(self):
        self.assertEqual(self.window.txt_notes.toPlainText(), 'โน้ตเดิม')
        self.window.txt_notes.setPlainText('โน้ตใหม่')
        self.window.txt_notes.document().setModified(True)
        self.assertTrue(self.window.save_current_note())
        self.db.save_note.assert_called_once_with(12, 1, 'โน้ตใหม่')
        self.window.go_to_page(1)
        self.db.get_note.assert_called_with(12, 2)
        self.assertEqual(self.window.current_page, 1)

    def test_failed_save_blocks_navigation(self):
        self.window.txt_notes.setPlainText('ห้ามหาย')
        self.window.txt_notes.document().setModified(True)
        self.db.save_note.side_effect = RuntimeError('offline')
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Save), \
             patch.object(QMessageBox, 'warning'):
            self.window.go_to_page(1)
        self.assertEqual(self.window.current_page, 0)
        self.assertEqual(self.window.spin_page.value(), 1)
        self.assertEqual(self.window.txt_notes.toPlainText(), 'ห้ามหาย')
        self.assertTrue(self.window.txt_notes.document().isModified())

    def test_failed_load_keeps_old_document(self):
        old = self.window.doc
        self.db.register_document.side_effect = RuntimeError('offline')
        with patch.object(QMessageBox, 'critical'):
            self.window.load_pdf(str(self.path))
        self.assertIs(self.window.doc, old)
        self.assertFalse(old.is_closed)

    def test_ai_uses_original_page_and_preserves_note(self):
        self.window.ai_context = (12, 1, 'test-model')
        self.window.ai_worker = SimpleNamespace(is_cancelled=False)
        self.window.go_to_page(1)
        self.window.on_ai_success('ผลสรุปหน้าแรก')
        self.db.add_summary.assert_called_once_with(12, 1, 'test-model', 'ผลสรุปหน้าแรก')
        self.assertEqual(self.window.txt_notes.toPlainText(), 'โน้ตเดิม')
        self.assertEqual(self.window.txt_summary.toPlainText(), '')
        self.window.ai_worker = None

    def test_failed_summary_can_be_retried(self):
        self.window.ai_context = (12, 1, 'test-model')
        self.window.ai_worker = SimpleNamespace(is_cancelled=False)
        self.db.add_summary.side_effect = RuntimeError('offline')
        with patch.object(QMessageBox, 'warning'):
            self.window.on_ai_success('ผลที่ต้องเก็บ')
        self.assertEqual(len(self.window.pending_summaries), 1)
        self.db.add_summary.side_effect = None
        self.window.retry_pending_summaries()
        self.assertEqual(self.window.pending_summaries, [])
        self.window.ai_worker = None

    def test_cancelled_ai_is_not_saved(self):
        self.window.ai_worker = SimpleNamespace(is_cancelled=True)
        self.window.on_ai_success('ผลที่ยกเลิก')
        self.db.add_summary.assert_not_called()
        self.window.ai_worker = None


if __name__ == '__main__':
    unittest.main()
