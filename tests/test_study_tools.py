"""ตรวจคำอ้างอิงที่แสดงให้ผู้ใช้และการเลือกหน้าเอกสาร"""
import json
import unittest

import pymupdf
from study_tools import read_citation, source_pages


class StudyTests(unittest.TestCase):
    def test_retrieve_and_verify(self):
        with pymupdf.open() as doc:
            doc.new_page().insert_text((30, 30), 'Overview')
            doc.new_page().insert_text((30, 30), 'LEFT JOIN keeps unmatched rows.')
            pages = source_pages(doc, 'LEFT JOIN', 0)
        self.assertEqual(next(iter(pages)), 2)
        data = dict(answer='เก็บแถวที่ไม่มีคู่', page=2, quote='keeps unmatched rows')
        self.assertEqual(read_citation(json.dumps(data), pages)[0], 2)
        for change in [dict(page=1), dict(page=9), dict(quote='invented')]:
            with self.assertRaises(ValueError):
                read_citation(json.dumps(data | change), pages)
