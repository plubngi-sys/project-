"""ทดสอบ timeout และการยกเลิกคำขอ AI โดยไม่ใช้โมเดลจริง"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import asyncio
import time
import unittest
from unittest.mock import patch
from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QTest
from project1 import OllamaWorker


class SlowClient:
    closed = False
    def __init__(self, **kwargs):
        pass
    async def __aenter__(self):
        return self
    async def __aexit__(self, *args):
        type(self).closed = True
    async def chat(self, **kwargs):
        await asyncio.sleep(5)
        return {'message': {'content': 'ผลที่ไม่ควรรับ'}}


class AIWorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def finish(self, worker):
        deadline = time.monotonic() + 2
        while worker.isRunning():
            if time.monotonic() > deadline:
                worker.cancel()
                worker.wait(2000)
                self.fail('AI worker ไม่หยุดตามเวลา')
            QTest.qWait(10)
        self.app.processEvents()

    def test_timeout_closes_client(self):
        SlowClient.closed = False
        errors, results = [], []
        worker = OllamaWorker('test', timeout=0.05)
        worker.error.connect(errors.append)
        worker.result.connect(results.append)
        with patch('project1.ollama.AsyncClient', SlowClient):
            worker.start()
            self.finish(worker)
        self.assertEqual(len(errors), 1)
        self.assertIn('เกินกำหนด', errors[0])
        self.assertEqual(results, [])
        self.assertTrue(SlowClient.closed)

    def test_cancel_interrupts_request_without_result(self):
        SlowClient.closed = False
        results, errors = [], []
        worker = OllamaWorker('test', timeout=10)
        worker.result.connect(results.append)
        worker.error.connect(errors.append)
        with patch('project1.ollama.AsyncClient', SlowClient):
            worker.start()
            QTest.qWait(50)
            worker.cancel()
            self.finish(worker)
        self.assertEqual(results, [])
        self.assertEqual(errors, [])
        self.assertTrue(SlowClient.closed)


if __name__ == '__main__':
    unittest.main()
